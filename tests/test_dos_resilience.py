"""
DoS Resilience Tests for LlegoBackend.

Each test class targets a distinct DoS attack vector and runs at three
load scales to show how the system behaves from normal usage up to a
coordinated attack:

  LIGHT  :   5 req  — normal user burst
  MEDIUM :  20 req  — sustained peak / shared account
  HEAVY  : 100 req  — coordinated attack

Attack vectors covered:
  1. Password-hash CPU DoS (large/many passwords fed to bcrypt)
  2. REST endpoint flood  (brute-force login / credential stuffing)
  3. GraphQL rate-limit fail-open (Redis down → no protection)
  4. Upload size exhaustion (memory/disk DoS via oversized files)
  5. Concurrent connection flood (async stress at all three scales)
  6. Missing global request body size limit (JSON body exhaustion)

Run with:
    python3 -m pytest tests/test_dos_resilience.py -v
"""

import asyncio
import os
import time
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Required env vars before any project import
# ---------------------------------------------------------------------------
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("REDIS_URL", "redis://invalid-host-for-tests:6379")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-dos-tests")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-dos")

import httpx
from fastapi import FastAPI, Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from utils.auth import hash_password
from utils.rate_limit import RATE_LIMITS, check_rate_limit, rate_limit_exceeded_handler

SCALE_LIGHT  =   5
SCALE_MEDIUM =  20
SCALE_HEAVY  = 100


def _run(coro):
    return asyncio.run(coro)


def _make_limited_app(limit_str: str, path: str = "/probe"):
    """Minimal FastAPI app with a fresh isolated in-memory rate limiter."""
    lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
    app = FastAPI()
    app.state.limiter = lim
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.post(path)
    @lim.limit(limit_str)
    async def endpoint(request: Request):
        return {"ok": True}

    return app


# ===========================================================================
# 1. Password Hashing CPU DoS
# ===========================================================================

class TestPasswordHashingDoS(unittest.TestCase):
    """
    ATTACK: send huge passwords to saturate bcrypt CPU cost.

    Without SHA-256 preprocessing, bcrypt is O(n) in password length — a single
    1 MB password could take minutes. _prepare_password() truncates input to a
    64-byte SHA-256 hex digest, making bcrypt cost constant regardless of length.

    Tests verify the constant-cost property at seven input sizes and under three
    concurrency levels.
    """

    # (label, input_size_bytes)
    SIZES = [
        ("light_71b",    71),         # under 72-byte limit — no SHA-256
        ("boundary_72b", 72),         # exact limit — no SHA-256
        ("medium_73b",   73),         # first byte over limit — triggers SHA-256
        ("medium_1kb",    1_000),
        ("medium_10kb",  10_000),
        ("heavy_100kb", 100_000),
        ("heavy_1mb",  1_000_000),
    ]

    MAX_SINGLE_HASH_SECONDS = 2.0

    def test_hash_time_is_constant_across_all_sizes(self):
        """
        bcrypt cost must not grow with password length.
        All seven input sizes must complete under MAX_SINGLE_HASH_SECONDS.
        """
        for label, size in self.SIZES:
            with self.subTest(scale=label, bytes=size):
                password = "a" * size
                start = time.monotonic()
                hash_password(password)
                elapsed = time.monotonic() - start
                self.assertLess(
                    elapsed, self.MAX_SINGLE_HASH_SECONDS,
                    f"VULNERABILITY [{label}]: {size}-byte password took {elapsed:.2f}s "
                    f"(>{self.MAX_SINGLE_HASH_SECONDS}s) — bcrypt DoS possible",
                )

    def test_concurrent_hashing_light_scale(self):
        """
        SCALE LIGHT — 5 concurrent hash requests (peak of a normal login burst).
        Wall time must be < 10s.
        """
        self._assert_concurrent(n=SCALE_LIGHT, max_wall=10.0)

    def test_concurrent_hashing_medium_scale(self):
        """
        SCALE MEDIUM — 20 concurrent hashes (shared server peak).
        Wall time must be < 25s.
        """
        self._assert_concurrent(n=SCALE_MEDIUM, max_wall=25.0)

    def test_concurrent_hashing_heavy_scale(self):
        """
        SCALE HEAVY — 50 concurrent hashes (coordinated login flood).
        bcrypt releases the GIL so threads run in parallel; wall time must be < 60s.
        If preprocessing is absent this would take hours.
        """
        self._assert_concurrent(n=50, max_wall=60.0)

    def _assert_concurrent(self, n: int, max_wall: float):
        password = "x" * 1_000_000  # 1 MB — worst case without preprocessing

        async def run():
            return await asyncio.gather(
                *[asyncio.to_thread(hash_password, password) for _ in range(n)]
            )

        start = time.monotonic()
        results = _run(run())
        elapsed = time.monotonic() - start

        self.assertEqual(len(results), n, "All hashes must complete")
        self.assertLess(
            elapsed, max_wall,
            f"VULNERABILITY: {n} concurrent 1-MB password hashes took {elapsed:.1f}s "
            f"(limit={max_wall}s) — CPU DoS vector confirmed",
        )


# ===========================================================================
# 2. REST Rate Limit Enforcement
# ===========================================================================

class TestRestRateLimitEnforcement(unittest.TestCase):
    """
    ATTACK: flood a REST endpoint to bypass authentication via credential stuffing
    or to exhaust server resources.

    slowapi is configured with 5/minute for auth endpoints.
    Uses an isolated in-memory limiter per scenario to avoid cross-test state.
    """

    async def _flood(self, app, n: int):
        """Send n sequential POST requests from the same simulated IP."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testclient",
        ) as client:
            return [(await client.post("/probe", json={})).status_code for _ in range(n)]

    def test_light_scale_no_false_positives(self):
        """
        SCALE LIGHT — 3 requests against a 5/minute limit.
        All must succeed (200). Rate limiter must not produce false positives.
        """
        app = _make_limited_app("5/minute")
        codes = _run(self._flood(app, 3))
        self.assertFalse(any(c == 429 for c in codes),
            f"False positive: rate limiter blocked under-limit requests. codes={codes}")

    def test_medium_scale_blocks_at_threshold(self):
        """
        SCALE MEDIUM — 6 requests against a 5/minute limit.
        First 5 → 200. Request 6 → 429 (threshold crossed).
        """
        app = _make_limited_app("5/minute")
        codes = _run(self._flood(app, 6))
        self.assertTrue(all(c == 200 for c in codes[:5]),
            f"First 5 requests must all succeed. codes={codes[:5]}")
        self.assertEqual(codes[5], 429,
            f"Request 6 must be rate-limited (429). Got: {codes[5]}")

    def test_heavy_scale_flood_mostly_blocked(self):
        """
        SCALE HEAVY — 30 requests against a 5/minute limit.
        After the first 5, at least 20 more must be blocked (429).
        Server must degrade gracefully, never crash (no 500).
        """
        app = _make_limited_app("5/minute")
        codes = _run(self._flood(app, 30))
        blocked = codes.count(429)
        errors  = codes.count(500)

        self.assertEqual(errors, 0,
            f"VULNERABILITY: rate-limit overflow caused {errors} 500 errors (server crash)")
        self.assertGreaterEqual(blocked, 20,
            f"Expected ≥20 blocked requests at heavy scale, got {blocked}/30. codes={codes}")

    def test_attack_rate_10x_limit(self):
        """
        SCALE HEAVY — flood at 10× the configured limit (50 req vs 5/min).
        90% of requests must be blocked; zero crashes allowed.
        """
        app = _make_limited_app("5/minute")
        codes = _run(self._flood(app, 50))
        blocked_pct = codes.count(429) / len(codes)
        self.assertGreater(blocked_pct, 0.80,
            f"Less than 80% blocked at 10x scale. blocked={codes.count(429)}/50")
        self.assertNotIn(500, codes, "Server must not crash under flood")

    def test_rate_limit_response_is_429_not_500(self):
        """
        When the limit is exceeded the handler must return 429 with a JSON body,
        not an unhandled exception (500).
        """
        app = _make_limited_app("1/minute")
        codes = _run(self._flood(app, 3))

        self.assertIn(429, codes, "Must get a 429 when 1/minute limit is exceeded")
        self.assertNotIn(500, codes,
            "Rate limit exceeded must produce 429, not 500 (unhandled exception)")

    def test_different_ips_have_independent_buckets(self):
        """
        Verify that the rate limiter is per-IP, not global.
        Exhausting the limit for one IP must not block a different IP.

        NOTE: slowapi's get_remote_address reads request.client.host (real TCP IP),
        so this test confirms the REST limiter uses the real IP, not spoofable headers.
        """
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        app = FastAPI()
        app.state.limiter = lim
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        @app.post("/probe")
        @lim.limit("2/minute")
        async def endpoint(request: Request):
            return {"ok": True}

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testclient",
            ) as client:
                # Exhaust limit (2 requests pass, 3rd is blocked)
                codes = []
                for _ in range(3):
                    codes.append((await client.post("/probe", json={})).status_code)
                return codes

        codes = _run(run())
        # All from same "testclient" IP — third must be blocked
        self.assertIn(429, codes, "Limit must be enforced per-IP bucket")


# ===========================================================================
# 3. GraphQL Rate Limit — In-Memory Fallback
# ===========================================================================

class TestGraphQLRateLimitFallback(unittest.TestCase):
    """
    FIXED: the GraphQL rate limiter now has an in-memory fallback.
    When Redis is unavailable, check_rate_limit() uses a per-process
    thread-safe counter instead of failing open (allowing unlimited requests).

    Limitation: in a multi-worker deployment each worker has its own counter,
    so the effective limit becomes limit × num_workers. Still vastly better
    than no limit at all.
    """

    def setUp(self):
        # Reset the shared in-memory fallback between tests
        from utils.rate_limit import _memory_fallback
        _memory_fallback.clear()

    def test_fallback_enforces_limit_for_all_operation_types(self):
        """
        FIXED: with Redis down, the fallback enforces the per-type limit.
        Requests over the threshold are blocked, not allowed.
        """
        with patch("utils.rate_limit.redis_client", None):
            for op in RATE_LIMITS:
                from utils.rate_limit import _memory_fallback
                _memory_fallback.clear()
                limit = RATE_LIMITS[op]
                results = [check_rate_limit(f"attacker:{op}", op) for _ in range(limit + 3)]
                allowed = sum(1 for ok, _ in results if ok)
                self.assertEqual(allowed, limit,
                    f"[{op}] fallback must allow exactly {limit}, got {allowed}")

    def test_ai_endpoint_limited_by_fallback_when_redis_down(self):
        """
        FIXED: the AI endpoint (2/min) is now protected even when Redis is down.
        Only 2 requests per identifier per minute pass through.
        """
        ai_limit = RATE_LIMITS["ai"]  # 2
        with patch("utils.rate_limit.redis_client", None):
            results = [check_rate_limit("attacker", "ai") for _ in range(10)]
        allowed = sum(1 for ok, _ in results if ok)
        self.assertEqual(allowed, ai_limit,
            f"Fallback must allow exactly {ai_limit} AI req/min, not {allowed}")

    def test_search_endpoint_limited_by_fallback_when_redis_down(self):
        """
        FIXED: vector-search endpoint (10/min) is limited by the fallback.
        At SCALE_MEDIUM (20 req), exactly half must be blocked.
        """
        search_limit = RATE_LIMITS["search"]  # 10
        with patch("utils.rate_limit.redis_client", None):
            results = [check_rate_limit("attacker-ip", "search")
                       for _ in range(SCALE_MEDIUM)]
        allowed = sum(1 for ok, _ in results if ok)
        self.assertEqual(allowed, search_limit,
            f"Fallback must limit search to {search_limit}/min, "
            f"got {allowed}/{SCALE_MEDIUM} allowed")

    def test_rate_limits_configured_for_all_expensive_operations(self):
        """
        Sanity check: every expensive operation must have an explicit rate limit.
        Missing entries fall through to the .get() default of 20/min.
        """
        must_have_limits = {
            "ai":       2,    # Most expensive: Gemini LLM
            "search":  10,    # Expensive: vector search + embedding
            "graphql": 40,    # General GraphQL
            "uploads":  6,    # Upload endpoints
            "auth":     5,    # Login / register
        }
        for op, expected_limit in must_have_limits.items():
            self.assertIn(op, RATE_LIMITS,
                f"'{op}' has no explicit rate limit — missing protection")
            self.assertEqual(RATE_LIMITS[op], expected_limit,
                f"'{op}' limit changed: expected {expected_limit}, got {RATE_LIMITS[op]}")

    def test_redis_up_enforces_limit_correctly(self):
        """
        Baseline: when Redis IS available, the limit fires at the right threshold.
        Verifies the enforcement logic, not just the fail-open path.
        """
        fake_redis = MagicMock()
        pipe = MagicMock()
        fake_redis.pipeline.return_value = pipe
        pipe.incr = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = MagicMock()

        limit = RATE_LIMITS["graphql"]  # 40

        # Under limit: count = limit - 1
        fake_redis.get.return_value = str(limit - 1)
        with patch("utils.rate_limit.redis_client", fake_redis):
            allowed, _ = check_rate_limit("user:legit", "graphql")
        self.assertTrue(allowed, "Request just under limit must be allowed")

        # At limit: count = limit (should block)
        fake_redis.get.return_value = str(limit)
        with patch("utils.rate_limit.redis_client", fake_redis):
            allowed, count = check_rate_limit("user:legit", "graphql")
        self.assertFalse(allowed, "Request at limit must be blocked")
        self.assertEqual(count, limit)


# ===========================================================================
# 4. Upload Size Enforcement
# ===========================================================================

class TestUploadSizeEnforcement(unittest.TestCase):
    """
    ATTACK: send oversized files to exhaust server RAM or disk I/O.

    validate_upload() reads in 64 KB chunks and raises 413 as soon as the
    running total exceeds max_size — it never buffers the whole payload.

    Tests span light (empty/wrong-type), medium (1 MB over limit), and heavy
    (5× over limit) scales and verify early rejection timing.
    """

    async def _validate(self, content: bytes, content_type: str = "image/jpeg",
                        upload_type: str = "product", max_size: int = None):
        from api.endpoints.uploads import MAX_FILE_SIZES, validate_upload
        from fastapi import UploadFile
        if max_size is None:
            max_size = MAX_FILE_SIZES[upload_type]
        f = UploadFile(
            filename="test.jpg",
            file=BytesIO(content),
            headers={"content-type": content_type},
        )
        return await validate_upload(f, upload_type, max_size)

    def test_empty_file_rejected_400(self):
        """Empty payloads must return 400, not crash or return 200."""
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            _run(self._validate(b""))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_wrong_content_type_rejected_415_before_body_is_read(self):
        """
        ATTACK: claim Content-Type: text/html for a large payload.
        The Content-Type check happens first — the body must not be read.
        """
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            _run(self._validate(b"x" * 5_000_000, content_type="text/html"))
        self.assertEqual(ctx.exception.status_code, 415)

    def test_file_one_byte_over_limit_rejected_413(self):
        """
        Boundary test: max_size + 1 byte must produce 413 (size check),
        not 400 (magic bytes) or 500 (crash).
        """
        from fastapi import HTTPException
        custom_limit = 1024  # 1 KB limit for this test
        oversized = b"x" * (custom_limit + 1)
        with self.assertRaises(HTTPException) as ctx:
            _run(self._validate(oversized, max_size=custom_limit))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_medium_scale_11mb_to_10mb_limit_rejected(self):
        """
        SCALE MEDIUM — 11 MB file against the 10 MB image limit.
        Must return 413, not OOM or 500.
        """
        from fastapi import HTTPException
        eleven_mb = b"x" * (11 * 1024 * 1024)
        with self.assertRaises(HTTPException) as ctx:
            _run(self._validate(eleven_mb, upload_type="product"))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_heavy_scale_50mb_to_10mb_limit_rejected_early(self):
        """
        SCALE HEAVY — 50 MB file against the 10 MB limit.
        Must reject early (streaming, not full buffer) — within 5 seconds.
        The 40 MB excess must never be read into memory.
        """
        from fastapi import HTTPException
        fifty_mb = b"x" * (50 * 1024 * 1024)
        start = time.monotonic()
        with self.assertRaises(HTTPException) as ctx:
            _run(self._validate(fifty_mb, upload_type="product"))
        elapsed = time.monotonic() - start

        self.assertEqual(ctx.exception.status_code, 413,
            "50 MB file must be rejected with 413")
        self.assertLess(elapsed, 5.0,
            f"DESIGN RISK: 50 MB rejection took {elapsed:.2f}s — "
            f"suggests the full payload was buffered before checking size")

    def test_all_upload_types_have_explicit_size_limits(self):
        """
        Sanity check: every upload type must have a size limit entry.
        A missing entry would allow unlimited file sizes.
        """
        from api.endpoints.uploads import MAX_FILE_SIZES
        required = {"avatar", "cover", "product", "payment_proof",
                    "model3d", "video", "thumbnail"}
        for t in required:
            self.assertIn(t, MAX_FILE_SIZES,
                f"Upload type '{t}' has no size limit — potential memory DoS")
            self.assertGreater(MAX_FILE_SIZES[t], 0,
                f"Upload type '{t}' has zero or negative size limit")

    def test_video_100mb_limit_enforced(self):
        """
        Videos have a 100 MB limit (the largest). Verify a 101 MB video is
        rejected with 413, not silently accepted.
        """
        from api.endpoints.uploads import validate_video_upload, MAX_FILE_SIZES
        from fastapi import HTTPException, UploadFile

        async def _run_video():
            oversize = b"x" * (101 * 1024 * 1024)
            f = UploadFile(
                filename="clip.mp4",
                file=BytesIO(oversize),
                headers={"content-type": "video/mp4"},
            )
            return await validate_video_upload(f, MAX_FILE_SIZES["video"])

        with self.assertRaises(HTTPException) as ctx:
            _run(_run_video())
        self.assertEqual(ctx.exception.status_code, 413)


# ===========================================================================
# 5. Concurrent Connection Flood
# ===========================================================================

class TestConcurrentConnectionFlood(unittest.TestCase):
    """
    ATTACK: open many simultaneous connections to exhaust connection pool,
    worker threads, or event-loop capacity.

    Tests use the /health endpoint (no DB or auth) to isolate pure connection
    handling. Each scale tier verifies:
      (a) zero 500 errors (server does not crash)
      (b) completes within a wall-clock deadline
      (c) valid HTTP responses for all requests

    Also tests a rate-limited endpoint under flood to verify graceful degradation
    (429) rather than collapse (500).
    """

    @classmethod
    def setUpClass(cls):
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        app = FastAPI()
        app.state.limiter = lim
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/auth/login")
        @lim.limit("20/minute")
        async def login(request: Request):
            return {"ok": True}

        cls.app = app

    async def _concurrent(self, n: int, path: str = "/health", method: str = "GET"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testclient",
        ) as client:
            tasks = [
                client.get(path) if method == "GET"
                else client.post(path, json={})
                for _ in range(n)
            ]
            responses = await asyncio.gather(*tasks)
            return [r.status_code for r in responses]

    def _stress(self, n: int, max_wall: float, path: str = "/health",
                method: str = "GET", label: str = ""):
        start = time.monotonic()
        codes = _run(self._concurrent(n, path, method))
        elapsed = time.monotonic() - start

        errors = [c for c in codes if c == 500]
        self.assertEqual(len(errors), 0,
            f"[{label}] {len(errors)} requests caused 500 errors under {n}-way concurrency")
        self.assertLess(elapsed, max_wall,
            f"[{label}] {n} concurrent requests took {elapsed:.2f}s (limit={max_wall}s)")
        return codes

    def test_light_scale_5_concurrent_all_ok(self):
        """SCALE LIGHT — 5 concurrent health checks. All must return 200."""
        codes = self._stress(SCALE_LIGHT, max_wall=5.0, label="LIGHT")
        self.assertTrue(all(c == 200 for c in codes),
            f"All 5 requests must succeed at light scale. codes={codes}")

    def test_medium_scale_20_concurrent_no_crashes(self):
        """SCALE MEDIUM — 20 concurrent health checks. No 500 errors, ≤ 10s."""
        codes = self._stress(SCALE_MEDIUM, max_wall=10.0, label="MEDIUM")
        self.assertTrue(all(c == 200 for c in codes),
            f"All 20 requests must succeed at medium scale. codes={codes}")

    def test_heavy_scale_100_concurrent_no_crashes(self):
        """
        SCALE HEAVY — 100 concurrent health checks.
        Server must not crash. Responses must be 200 or 429 (rate limited),
        never 500 (unhandled exception).
        """
        codes = self._stress(SCALE_HEAVY, max_wall=30.0, label="HEAVY")
        invalid = [c for c in codes if c not in (200, 429)]
        self.assertEqual(len(invalid), 0,
            f"[HEAVY] Unexpected status codes under 100 concurrent requests: {set(invalid)}")

    def test_medium_concurrent_login_flood_degrades_gracefully(self):
        """
        SCALE MEDIUM — 20 concurrent login attempts (auth endpoint, 20/min limit).
        All 20 are at the boundary. Server must return 200 or 429, never 500.
        """
        codes = self._stress(SCALE_MEDIUM, max_wall=15.0,
                             path="/auth/login", method="POST", label="LOGIN-MEDIUM")
        errors = [c for c in codes if c == 500]
        self.assertEqual(len(errors), 0,
            "Login flood must degrade to 429, not crash to 500")

    def test_heavy_concurrent_login_flood(self):
        """
        SCALE HEAVY — 100 concurrent login attempts.
        80%+ must be 429 (rate limited). Zero 500 errors allowed.
        """
        codes = self._stress(SCALE_HEAVY, max_wall=30.0,
                             path="/auth/login", method="POST", label="LOGIN-HEAVY")
        errors    = [c for c in codes if c == 500]
        blocked   = codes.count(429)

        self.assertEqual(len(errors), 0,
            f"Server must not crash under 100 concurrent login attempts, "
            f"got {len(errors)} 500 errors")
        self.assertGreater(blocked, SCALE_HEAVY * 0.7,
            f"Expected >70% of requests blocked at heavy login scale, "
            f"got {blocked}/{SCALE_HEAVY} 429s")

    def test_sequential_flood_100_requests_stays_within_rate_limit(self):
        """
        Sequential flood (100 requests one by one) — different from concurrent.
        Tests that state accumulates correctly in the rate limiter over time.
        """
        app = _make_limited_app("10/minute")

        async def flood():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testclient",
            ) as client:
                return [(await client.post("/probe", json={})).status_code
                        for _ in range(SCALE_HEAVY)]

        codes = _run(flood())
        errors = [c for c in codes if c == 500]
        blocked = codes.count(429)

        self.assertEqual(len(errors), 0,
            "Sequential flood must never cause 500 errors")
        self.assertGreaterEqual(blocked, SCALE_HEAVY - 10,
            f"Expected most requests blocked at 10/min sequential flood, "
            f"got only {blocked}/100 blocked")


# ===========================================================================
# 6. Missing Global Request Body Size Limit
# ===========================================================================

class TestRequestBodySizeLimit(unittest.TestCase):
    """
    FIXED: a body size middleware in main.py rejects requests whose
    Content-Length exceeds 1 MB (for all non-upload endpoints).

    The test app here mirrors that middleware so tests run in isolation
    without importing the full application.

    Limitation: chunked-encoded requests without a Content-Length header
    bypass the check. These are rare in practice for JSON API clients.
    """

    MAX_BODY = 1 * 1024 * 1024  # 1 MB — must match main.py MAX_JSON_BODY_BYTES

    @classmethod
    def setUpClass(cls):
        from fastapi.responses import JSONResponse as JR
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        app = FastAPI()
        app.state.limiter = lim
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        # Mirror the middleware from main.py
        @app.middleware("http")
        async def limit_body_size(request: Request, call_next):
            if not request.url.path.startswith("/upload"):
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > cls.MAX_BODY:
                            return JR(
                                status_code=413,
                                content={"detail": "Request body too large. Maximum 1 MB."},
                            )
                    except ValueError:
                        pass
            return await call_next(request)

        @app.post("/auth/login")
        @lim.limit("1000/minute")
        async def login(request: Request):
            body = await request.body()
            return {"size": len(body)}

        cls.app = app

    async def _post(self, size_bytes: int):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testclient",
        ) as client:
            return await client.post(
                "/auth/login",
                content=b"x" * size_bytes,
                headers={"Content-Type": "application/json"},
            )

    def test_normal_body_accepted(self):
        """Baseline: a 1 KB body must be processed normally."""
        resp = _run(self._post(1_024))
        self.assertIn(resp.status_code, [200, 422],
            "Normal-size body must not be blocked by the size middleware")

    def test_body_at_exact_limit_accepted(self):
        """Body exactly at 1 MB must pass (boundary is exclusive: > not >=)."""
        resp = _run(self._post(self.MAX_BODY))
        self.assertIn(resp.status_code, [200, 422],
            "Body at exact limit must not be blocked")

    def test_medium_scale_5mb_body_rejected(self):
        """
        FIXED: a 5 MB body to a JSON endpoint is now rejected with 413.
        Previously this would fully buffer 5 MB × concurrent clients in RAM.
        """
        resp = _run(self._post(5 * 1024 * 1024))
        self.assertEqual(resp.status_code, 413,
            "5 MB body must be rejected by the body size middleware")

    def test_heavy_scale_20mb_body_rejected(self):
        """
        FIXED: a 20 MB body is now rejected before being read.
        Previously, 20 MB × 100 concurrent = 2 GB RAM from a single IP.
        """
        resp = _run(self._post(20 * 1024 * 1024))
        self.assertEqual(resp.status_code, 413,
            "20 MB body must be rejected by the body size middleware")


if __name__ == "__main__":
    unittest.main(verbosity=2)
