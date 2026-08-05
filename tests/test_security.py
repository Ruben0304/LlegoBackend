"""Security tests for LlegoBackend.

Covers:
  1. JWT token security  (forgery, expiry, algorithm-none attack, role escalation)
  2. Password hashing    (bcrypt + SHA-256 preprocessing for long passwords)
  3. GraphQL auth helpers (require_auth / require_role)
  4. Admin endpoint       (static bearer-token protection)
  5. Upload file validation (MIME spoofing, magic bytes, empty/oversized files)
  6. Upload endpoint auth   (unauthenticated → 401)

Run with:
    python3 -m pytest tests/test_security.py -v
"""

import asyncio
import base64
import json
import os
import unittest
from datetime import timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Set required env vars BEFORE any project import so pydantic-settings
# picks them up in its @lru_cache singleton.
# ---------------------------------------------------------------------------
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("REDIS_URL", "redis://invalid-host-for-tests:6379")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-unit-tests-only")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-unit-tests-only")

import httpx
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from utils.auth import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from utils.rate_limit import limiter, rate_limit_exceeded_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_app(*routers):
    """Create a minimal FastAPI app for HTTP-level security tests."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    for r in routers:
        app.include_router(r)
    return app


def _run_async(coro):
    """Execute a coroutine synchronously (safe for unittest.TestCase methods)."""
    return asyncio.run(coro)


def _make_graphql_info(user_id=None, user_role=None):
    """Return a mock Strawberry Info with a dict-like context."""
    context = {"user_id": user_id, "user_role": user_role}
    info = MagicMock()
    info.context = context
    return info


def _forge_unsigned_jwt(payload: dict) -> str:
    """Build a structurally valid but unsigned JWT (alg=none attack)."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{body}."


# ---------------------------------------------------------------------------
# 1. JWT Token Security
# ---------------------------------------------------------------------------

class TestJWTTokenSecurity(unittest.TestCase):
    """JWT creation and validation — core of the authentication layer."""

    def test_valid_token_roundtrips(self):
        """A freshly created token must decode back to the original payload."""
        token = create_access_token({"user_id": "user-42", "role": "customer"})
        payload = decode_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], "user-42")
        self.assertEqual(payload["role"], "customer")

    def test_expired_token_returns_none(self):
        """A token with a past expiry must be rejected."""
        token = create_access_token(
            {"user_id": "user-42"}, expires_delta=timedelta(seconds=-1)
        )
        self.assertIsNone(decode_access_token(token))

    def test_tampered_signature_returns_none(self):
        """Flipping one character in the signature must invalidate the token."""
        token = create_access_token({"user_id": "user-42"})
        parts = token.rsplit(".", 1)
        bad_sig = parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B")
        tampered = f"{parts[0]}.{bad_sig}"
        self.assertIsNone(decode_access_token(tampered))

    def test_wrong_secret_returns_none(self):
        """A token signed with a different secret must be rejected."""
        # Bypass create_access_token so we can use a different secret
        try:
            import jwt as pyjwt
            other_token = pyjwt.encode(
                {"user_id": "user-42", "exp": 9999999999},
                "wrong-secret",
                algorithm=ALGORITHM,
            )
        except Exception:
            from jose import jwt as jose_jwt
            other_token = jose_jwt.encode(
                {"user_id": "user-42", "exp": 9999999999},
                "wrong-secret",
                algorithm=ALGORITHM,
            )
        self.assertIsNone(decode_access_token(other_token))

    def test_algorithm_none_attack_rejected(self):
        """An unsigned alg=none token must never be accepted."""
        forged = _forge_unsigned_jwt({"user_id": "hacker", "role": "admin"})
        self.assertIsNone(decode_access_token(forged))

    def test_role_escalation_forged_token_rejected(self):
        """A token claiming admin role but signed incorrectly must be rejected."""
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(
            json.dumps({"user_id": "attacker", "role": "admin"}).encode()
        ).rstrip(b"=").decode()
        forged = f"{header}.{body}.invalid_sig"
        self.assertIsNone(decode_access_token(forged))

    def test_empty_string_token_returns_none(self):
        self.assertIsNone(decode_access_token(""))

    def test_none_token_returns_none(self):
        self.assertIsNone(decode_access_token(None))

    def test_random_garbage_returns_none(self):
        self.assertIsNone(decode_access_token("definitely.not.a.valid.jwt"))

    def test_user_id_preserved_across_encode_decode(self):
        """user_id must survive the encode → decode roundtrip unchanged."""
        user_id = "507f1f77bcf86cd799439011"
        token = create_access_token({"user_id": user_id, "role": "admin"})
        payload = decode_access_token(token)
        self.assertEqual(payload["user_id"], user_id)


# ---------------------------------------------------------------------------
# 2. Password Security
# ---------------------------------------------------------------------------

class TestPasswordSecurity(unittest.TestCase):
    """bcrypt hashing with SHA-256 preprocessing for passwords > 72 bytes."""

    def test_hash_is_not_plaintext(self):
        h = hash_password("mysecretpassword")
        self.assertNotEqual(h, "mysecretpassword")
        self.assertTrue(h.startswith("$2b$"), "Expected bcrypt hash format")

    def test_correct_password_verifies(self):
        h = hash_password("correct-horse-battery-staple")
        self.assertTrue(verify_password("correct-horse-battery-staple", h))

    def test_wrong_password_fails(self):
        h = hash_password("correct-horse-battery-staple")
        self.assertFalse(verify_password("wrong-password", h))

    def test_each_hash_is_uniquely_salted(self):
        """bcrypt must produce a different hash every call (unique salts)."""
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password("same-password", h1))
        self.assertTrue(verify_password("same-password", h2))

    def test_long_password_exceeding_72_bytes_verifies(self):
        """Passwords longer than bcrypt's 72-byte limit must verify correctly."""
        long_pass = "a" * 100
        h = hash_password(long_pass)
        self.assertTrue(verify_password(long_pass, h))

    def test_two_long_passwords_differing_by_one_char_are_distinct(self):
        """SHA-256 pre-hashing must preserve uniqueness for long passwords.

        Without SHA-256 preprocessing, bcrypt silently truncates at 72 bytes,
        making 'aaa...a' (73 chars) identical to 'aaa...a' + 'b' (the 73rd char
        differs but bcrypt never sees it). The preprocessing prevents this.
        """
        base = "a" * 73
        variant = "a" * 72 + "b"
        h_base = hash_password(base)
        h_variant = hash_password(variant)
        self.assertFalse(verify_password(variant, h_base), "Truncation bug detected")
        self.assertFalse(verify_password(base, h_variant), "Truncation bug detected")

    def test_none_password_fails_verify(self):
        h = hash_password("somepassword")
        self.assertFalse(verify_password(None, h))

    def test_empty_password_does_not_match_nonempty_hash(self):
        h = hash_password("nonempty")
        self.assertFalse(verify_password("", h))

    def test_none_hash_fails_verify(self):
        self.assertFalse(verify_password("password", None))


# ---------------------------------------------------------------------------
# 3. GraphQL Auth Helpers
# ---------------------------------------------------------------------------

class TestGraphQLAuthHelpers(unittest.TestCase):
    """require_auth / require_role must enforce authentication and roles."""

    @classmethod
    def setUpClass(cls):
        # On system Python 3.9 with mismatched pydantic/strawberry versions the
        # first `from strawberry.types import Info` fails, but it primes the
        # strawberry submodule cache so the second attempt succeeds. Pre-warm
        # the cache here so individual test methods can import cleanly.
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            try:
                import utils.graphql_auth  # noqa: F401
            except ImportError:
                pass

    # ------------------------------------------------------------------
    # apply_optional_jwt
    # ------------------------------------------------------------------

    def test_apply_optional_jwt_with_no_token_returns_none(self):
        from utils.graphql_auth import apply_optional_jwt
        info = _make_graphql_info()
        result = apply_optional_jwt(None, info)
        self.assertIsNone(result)

    def test_apply_optional_jwt_with_invalid_token_raises(self):
        from utils.graphql_auth import apply_optional_jwt
        info = _make_graphql_info()
        with self.assertRaises(Exception) as ctx:
            apply_optional_jwt("not-a-valid-jwt", info)
        self.assertIn("Invalid JWT", str(ctx.exception))

    def test_apply_optional_jwt_with_valid_token_sets_user_id(self):
        from utils.graphql_auth import apply_optional_jwt
        with patch("utils.graphql_auth.decode_access_token") as mock_decode:
            mock_decode.return_value = {"user_id": "user-99", "role": "customer"}
            info = _make_graphql_info()
            uid = apply_optional_jwt("valid-token", info)
        self.assertEqual(uid, "user-99")
        self.assertEqual(info.context["user_id"], "user-99")

    # ------------------------------------------------------------------
    # require_auth
    # ------------------------------------------------------------------

    def test_require_auth_raises_without_jwt(self):
        from utils.graphql_auth import require_auth
        info = _make_graphql_info()
        with self.assertRaises(Exception) as ctx:
            require_auth(None, info)
        self.assertIn("requerida", str(ctx.exception).lower())

    def test_require_auth_raises_with_invalid_jwt(self):
        from utils.graphql_auth import require_auth
        info = _make_graphql_info()
        with self.assertRaises(Exception):
            require_auth("garbage-token", info)

    def test_require_auth_succeeds_with_valid_jwt(self):
        from utils.graphql_auth import require_auth
        with patch("utils.graphql_auth.decode_access_token") as mock_decode:
            mock_decode.return_value = {"user_id": "user-77", "role": "customer"}
            info = _make_graphql_info()
            uid = require_auth("valid-token", info)
        self.assertEqual(uid, "user-77")

    # ------------------------------------------------------------------
    # require_role
    # ------------------------------------------------------------------

    def test_require_role_allows_matching_role(self):
        from utils.graphql_auth import require_role
        with patch("utils.graphql_auth.decode_access_token") as mock_decode:
            mock_decode.return_value = {"user_id": "admin-1", "role": "admin"}
            info = _make_graphql_info()
            uid = require_role("valid-token", info, ["admin"])
        self.assertEqual(uid, "admin-1")

    def test_require_role_allows_any_role_in_list(self):
        from utils.graphql_auth import require_role
        with patch("utils.graphql_auth.decode_access_token") as mock_decode:
            mock_decode.return_value = {"user_id": "mgr-1", "role": "manager"}
            info = _make_graphql_info()
            uid = require_role("valid-token", info, ["admin", "manager"])
        self.assertEqual(uid, "mgr-1")

    def test_require_role_denies_wrong_role(self):
        from utils.graphql_auth import require_role
        with patch("utils.graphql_auth.decode_access_token") as mock_decode:
            mock_decode.return_value = {"user_id": "user-1", "role": "customer"}
            info = _make_graphql_info()
            with self.assertRaises(Exception) as ctx:
                require_role("valid-token", info, ["admin"])
        self.assertIn("denegado", str(ctx.exception).lower())

    def test_require_role_denies_missing_jwt(self):
        from utils.graphql_auth import require_role
        info = _make_graphql_info()
        with self.assertRaises(Exception):
            require_role(None, info, ["admin"])


# ---------------------------------------------------------------------------
# 4. Admin Endpoint Authentication
# ---------------------------------------------------------------------------

class TestAdminEndpointAuth(unittest.TestCase):
    """Admin /admin/* endpoints must only accept the correct static API key."""

    @classmethod
    def setUpClass(cls):
        from api.endpoints.admin_payouts import router as admin_router
        cls.app = _build_test_app(admin_router)

    async def _get(self, headers=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            return await client.get("/admin/pending-payouts", headers=headers or {})

    def test_no_auth_header_returns_401(self):
        resp = _run_async(self._get())
        self.assertEqual(resp.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        resp = _run_async(self._get({"Authorization": "Bearer wrong-key"}))
        self.assertEqual(resp.status_code, 401)

    def test_user_jwt_not_accepted_as_admin_key(self):
        """A valid user JWT must not be accepted in place of the admin API key."""
        user_token = create_access_token({"user_id": "user-1", "role": "admin"})
        resp = _run_async(self._get({"Authorization": f"Bearer {user_token}"}))
        self.assertEqual(resp.status_code, 401)

    def test_missing_admin_key_config_returns_503(self):
        """When ADMIN_API_KEY is not configured on the server, return 503."""
        with patch("api.endpoints.admin_payouts.settings") as m:
            m.admin_api_key = ""
            resp = _run_async(self._get({"Authorization": "Bearer anything"}))
        self.assertEqual(resp.status_code, 503)

    def test_correct_api_key_passes_auth_layer(self):
        """The correct key must pass the auth dependency (repo may fail after)."""
        with patch("api.endpoints.admin_payouts.settings") as m:
            m.admin_api_key = "test-admin-key-unit-tests-only"
            # Mock repo to avoid needing a real DB
            with patch("api.endpoints.admin_payouts.payouts_repo") as mock_repo:
                mock_repo.get_pending = AsyncMock(return_value=[])
                mock_repo.count_pending = AsyncMock(return_value=0)
                resp = _run_async(
                    self._get({"Authorization": "Bearer test-admin-key-unit-tests-only"})
                )
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 5. Upload File Validation (no HTTP needed)
# ---------------------------------------------------------------------------

class TestUploadFileValidation(unittest.TestCase):
    """Magic-byte and MIME validation for uploaded files."""

    def _sig(self, content: bytes):
        from api.endpoints.uploads import validate_image_signature
        return validate_image_signature(content)

    def test_valid_jpeg_detected(self):
        jpeg_magic = b"\xff\xd8\xff" + b"\x00" * 20
        self.assertEqual(self._sig(jpeg_magic), "image/jpeg")

    def test_valid_png_detected(self):
        png_magic = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        self.assertEqual(self._sig(png_magic), "image/png")

    def test_valid_webp_detected(self):
        webp_magic = b"RIFF" + b"\x00" * 4 + b"WEBP"
        self.assertEqual(self._sig(webp_magic), "image/webp")

    def test_valid_gif_detected(self):
        gif_magic = b"GIF89a" + b"\x00" * 20
        self.assertEqual(self._sig(gif_magic), "image/gif")

    def test_non_image_bytes_return_none(self):
        """A PHP/HTML file disguised as an image must not pass validation."""
        php_content = b"<?php echo 'evil'; ?>" + b"\x00" * 30
        self.assertIsNone(self._sig(php_content))

    def test_executable_bytes_return_none(self):
        """An ELF binary disguised as an image must not pass validation."""
        elf_magic = b"\x7fELF" + b"\x00" * 20
        self.assertIsNone(self._sig(elf_magic))

    def test_too_short_content_returns_none(self):
        """Files smaller than 12 bytes cannot be validated."""
        self.assertIsNone(self._sig(b"\xff\xd8"))

    def test_empty_content_returns_none(self):
        self.assertIsNone(self._sig(b""))

    def test_jpeg_magic_with_png_extension_is_detected_as_jpeg(self):
        """Actual content must take precedence over declared type."""
        jpeg_magic = b"\xff\xd8\xff" + b"\x00" * 20
        # validate_image_signature only looks at bytes, not extension
        self.assertEqual(self._sig(jpeg_magic), "image/jpeg")


# ---------------------------------------------------------------------------
# 6. Upload Endpoint Authentication
# ---------------------------------------------------------------------------

class TestUploadEndpointAuth(unittest.TestCase):
    """Upload endpoints must reject requests without a valid JWT."""

    @classmethod
    def setUpClass(cls):
        # Mock S3 upload so tests don't need real AWS
        cls._s3_patcher = patch("api.endpoints.uploads.upload_file", new=AsyncMock(return_value="path/to/img.jpg"))
        cls._s3_patcher.start()
        cls._presigned_patcher = patch("api.endpoints.uploads.generate_presigned_url", return_value="https://cdn.example.com/img.jpg")
        cls._presigned_patcher.start()

        from api.endpoints.uploads import router as uploads_router
        cls.app = _build_test_app(uploads_router)

    @classmethod
    def tearDownClass(cls):
        cls._s3_patcher.stop()
        cls._presigned_patcher.stop()

    def _upload(self, endpoint: str, headers=None):
        """POST a minimal fake JPEG to the given upload endpoint."""
        fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 50
        files = {"image": ("test.jpg", BytesIO(fake_jpeg), "image/jpeg")}

        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.post(endpoint, files=files, headers=headers or {})

        return _run_async(_do())

    def test_upload_without_any_auth_returns_401(self):
        resp = self._upload("/upload/user/avatar")
        self.assertEqual(resp.status_code, 401)

    def test_upload_with_invalid_jwt_returns_401(self):
        resp = self._upload(
            "/upload/user/avatar",
            headers={"Authorization": "Bearer not.a.real.jwt"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_upload_without_bearer_scheme_returns_401(self):
        token = create_access_token({"user_id": "user-1"})
        resp = self._upload(
            "/upload/user/avatar",
            headers={"Authorization": token},  # missing "Bearer " prefix
        )
        self.assertEqual(resp.status_code, 401)

    def test_upload_branch_avatar_without_auth_returns_401(self):
        resp = self._upload("/upload/branch/avatar")
        self.assertEqual(resp.status_code, 401)

    def test_upload_product_image_without_auth_returns_401(self):
        fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 50
        files = {"image": ("product.jpg", BytesIO(fake_jpeg), "image/jpeg")}

        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                return await client.post("/upload/product/image", files=files)

        resp = _run_async(_do())
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
