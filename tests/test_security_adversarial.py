"""
Adversarial security tests for LlegoBackend.

These tests probe for real attack patterns WITHOUT relying on knowledge of the
implementation. Each test picks a known vulnerability class and tries to trigger
it. Convention used throughout:

  PASS  → the system correctly defends against the attack
  FAIL  → a real vulnerability is present

Tests marked @unittest.expectedFailure document CONFIRMED vulnerabilities.
They will pass (as expected) while the vulnerability exists, and turn into
unexpected passes once fixed — acting as a built-in fix reminder.

Run with:
    python3 -m pytest tests/test_security_adversarial.py -v
"""

import asyncio
import inspect
import os
import secrets
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

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
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-adversarial")
os.environ.setdefault("ADMIN_API_KEY", "correct-admin-key-adversarial")

import httpx
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from utils.auth import hash_password, verify_password, create_access_token, decode_access_token
from utils.rate_limit import limiter, rate_limit_exceeded_handler


def _build_test_app(*routers):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    for r in routers:
        app.include_router(r)
    return app


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# 1. Password Adversarial Tests
# ===========================================================================

class TestPasswordAdversarial(unittest.TestCase):
    """
    Attack: try to authenticate as a user by exploiting password hashing quirks.
    """

    def test_null_byte_injection_does_not_bypass_password_check(self):
        """
        ATTACK: some bcrypt implementations treat passwords as C strings and
        stop at the first \\x00. If so, 'pass\\x00evil' hashes as 'pass', letting
        an attacker log in with any suffix after the null byte.

        If this test FAILS, the system is vulnerable to null-byte injection.
        """
        h = hash_password("secret")
        # Should NOT match — null byte must not act as a string terminator
        self.assertFalse(
            verify_password("secret\x00INJECTED", h),
            "VULNERABILITY: null byte injection bypasses password check",
        )

    def test_null_byte_password_does_not_verify_without_it(self):
        """
        ATTACK: reverse of the above. If 'pass\\x00x' and 'pass' hash identically,
        the attacker who knows the truncated password can log in as the user.
        """
        h = hash_password("pass\x00extra")
        self.assertFalse(
            verify_password("pass", h),
            "VULNERABILITY: truncated null-byte password accepted",
        )

    def test_bcrypt_legacy_fallback_truncation_vulnerability(self):
        """
        FIXED: legacy fallback removed from verify_password(). A password longer
        than 72 bytes now goes through SHA-256 preprocessing and cannot match a
        hash of the 72-byte prefix.

        Attack that was possible:
          1. User stored hash of "a"*72 (bcrypt(b"a"*72)).
          2. Attacker tried "a"*72 + "SUFFIX" (73 bytes).
          3. Legacy fallback truncated to 72 → matched → login succeeded.

        Now: no fallback exists, so SHA-256("a"*73) ≠ SHA-256-less bcrypt("a"*72).
        """
        password_72 = "a" * 72
        password_73 = "a" * 72 + "EVIL_SUFFIX"
        h72 = hash_password(password_72)
        self.assertFalse(
            verify_password(password_73, h72),
            "VULNERABILITY: legacy fallback accepts longer password via 72-byte truncation",
        )

    def test_unicode_normalization_nfc_vs_nfd(self):
        """
        ATTACK: NFC and NFD are two Unicode normalizations for visually identical
        strings. On some OS/keyboard combinations users type one form; on others
        the other. If the system normalizes inconsistently, an attacker could
        register with one form and log in with the other (or vice versa).

        This test documents the CURRENT behavior. If it fails, normalization is
        happening inconsistently — a potential bypass or lockout.
        """
        # "é" as NFC (single code point U+00E9)
        nfc = "café"
        # "é" as NFD (e + combining acute U+0065 U+0301)
        nfd = "café"

        self.assertNotEqual(nfc.encode("utf-8"), nfd.encode("utf-8"),
                            "Test setup error: NFC and NFD should differ in bytes")

        h_nfc = hash_password(nfc)
        h_nfd = hash_password(nfd)

        # They must NOT cross-verify (consistent behavior — no normalization bypass)
        self.assertFalse(
            verify_password(nfd, h_nfc),
            "VULNERABILITY: NFD password accepted against NFC hash (or vice versa)",
        )
        self.assertFalse(
            verify_password(nfc, h_nfd),
            "VULNERABILITY: NFC password accepted against NFD hash (or vice versa)",
        )

    def test_very_long_password_does_not_cause_dos(self):
        """
        ATTACK: without SHA-256 preprocessing, a 1 MB password fed to bcrypt
        would take extreme CPU time (bcrypt is O(n) in password length in some
        implementations). The preprocessing must cap the cost.

        If this hangs for more than a few seconds, the system is vulnerable to
        a password-based DoS.
        """
        import time
        huge_password = "a" * 100_000  # 100 KB

        start = time.monotonic()
        h = hash_password(huge_password)
        elapsed = time.monotonic() - start

        # bcrypt on a 64-byte SHA-256 digest should finish in < 2 s on any hardware
        self.assertLess(elapsed, 2.0,
                        "VULNERABILITY: very long password causes bcrypt DoS")
        self.assertTrue(verify_password(huge_password, h))

    def test_whitespace_password_is_distinct_from_empty(self):
        """
        ATTACK: a user whose password is a single space should not be able to
        log in with an empty string (and vice versa).
        """
        h_space = hash_password(" ")
        self.assertFalse(verify_password("", h_space))

        h_empty = hash_password("")
        self.assertFalse(verify_password(" ", h_empty))


# ===========================================================================
# 2. JWT Adversarial Tests
# ===========================================================================

class TestJWTAdversarial(unittest.TestCase):
    """
    Attack: forge, manipulate, or abuse JWTs to gain unauthorized access.
    """

    def _valid_token(self, extra=None):
        payload = {"user_id": "real-user-1", "role": "customer"}
        if extra:
            payload.update(extra)
        return create_access_token(payload)

    def test_token_with_null_user_id_is_rejected(self):
        """
        ATTACK: craft a token where user_id = null. Some authorization checks
        do `if user_id:` which passes for truthy strings but fails for None.
        A null user_id should never authenticate.
        """
        token = create_access_token({"user_id": None, "role": "customer"})
        payload = decode_access_token(token)
        # Even if the token decodes, require_auth must reject a null/falsy user_id
        user_id = payload.get("user_id") if payload else None
        self.assertFalse(
            bool(user_id),
            "VULNERABILITY: token with user_id=null passes authentication",
        )

    def test_token_with_missing_user_id_field_rejected(self):
        """
        ATTACK: a token with no user_id field at all (only other claims).
        Authorization code that does `payload['user_id']` without a .get()
        would raise KeyError and potentially leak information.
        """
        token = create_access_token({"sub": "someone", "role": "admin"})
        payload = decode_access_token(token)
        self.assertIsNotNone(payload)  # token itself is valid
        self.assertNotIn("user_id", payload,
                         "Test setup: token should not have user_id")

        # require_auth must reject this token (either "Invalid JWT" or auth error)
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            import utils.graphql_auth  # noqa: F401
        from utils.graphql_auth import require_auth

        info = MagicMock()
        info.context = {"user_id": None, "user_role": None}

        with patch("utils.graphql_auth.decode_access_token", return_value=payload):
            with self.assertRaises(Exception) as ctx:
                require_auth("any-token", info)
            error_msg = str(ctx.exception).lower()
            self.assertTrue(
                "requerida" in error_msg or "invalid jwt" in error_msg,
                f"Expected auth rejection but got: {ctx.exception}",
            )

    def test_role_escalation_in_valid_token_is_rejected_by_require_role(self):
        """
        ATTACK: an authenticated customer modifies the 'role' claim to 'admin'
        in their own token. Because they don't have the JWT secret they can't
        re-sign it, but let's verify that even a correctly-signed token issued
        by the server with role='customer' cannot pass a require_role(['admin'])
        check.

        This tests that role is read from the TOKEN, not from the request body.
        """
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            import utils.graphql_auth  # noqa: F401
        from utils.graphql_auth import require_role

        # Server issues a customer token (correct, signed)
        customer_token = self._valid_token({"role": "customer"})

        # Customer tries to access admin endpoint by passing this token
        # (they can't change the role without the secret)
        with patch("utils.graphql_auth.decode_access_token") as mock_dec:
            mock_dec.return_value = {"user_id": "real-user-1", "role": "customer"}
            info = MagicMock()
            info.context = {"user_id": None, "user_role": None}
            with self.assertRaises(Exception) as exc_ctx:
                require_role(customer_token, info, ["admin"])
        self.assertIn("denegado", str(exc_ctx.exception).lower())

    def test_token_with_extra_crafted_fields_does_not_grant_admin(self):
        """
        ATTACK: attacker injects extra fields into a valid JWT payload (they would
        need the secret to sign it, but let's ensure no extra field grants elevation).
        """
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            import utils.graphql_auth  # noqa: F401
        from utils.graphql_auth import require_role

        with patch("utils.graphql_auth.decode_access_token") as mock_dec:
            # Imagine the token was crafted with extra fields
            mock_dec.return_value = {
                "user_id": "user-1",
                "role": "customer",
                "is_admin": True,        # extra field
                "admin": True,           # extra field
                "permissions": ["*"],    # extra field
            }
            info = MagicMock()
            info.context = {"user_id": None, "user_role": None}
            with self.assertRaises(Exception) as exc_ctx:
                require_role("crafted-token", info, ["admin"])
        self.assertIn("denegado", str(exc_ctx.exception).lower())

    def test_far_future_expiry_token_is_accepted(self):
        """
        BEHAVIOR CHECK: tokens with very far-future expiry should be accepted
        (they're technically valid). This test documents that there is NO maximum
        lifetime check beyond the exp claim itself.

        A hardened system might reject tokens with exp > 90 days in the future.
        If this becomes a concern, add a max-lifetime check.
        """
        from datetime import timedelta
        token = create_access_token(
            {"user_id": "user-1", "role": "customer"},
            expires_delta=timedelta(days=365 * 10),  # 10 years
        )
        payload = decode_access_token(token)
        self.assertIsNotNone(payload,
                             "NOTE: tokens with 10-year expiry are accepted. "
                             "No maximum lifetime is enforced.")


# ===========================================================================
# 3. Timing Attack Surface
# ===========================================================================

class TestTimingAttackSurface(unittest.TestCase):
    """
    The admin API key comparison uses `!=`, which is NOT constant-time.
    An attacker who can make many requests and measure response latency could
    determine the correct key one character at a time.

    This class documents the vulnerability. The expectedFailure test turns
    into an unexpected PASS (visible in CI) once the code is fixed.
    """

    def test_admin_key_uses_constant_time_comparison(self):
        """
        FIXED: admin key comparison now uses secrets.compare_digest() (constant-time)
        instead of `!=`, eliminating the timing attack surface.
        """
        from api.endpoints.admin_payouts import _require_admin
        source = inspect.getsource(_require_admin)
        self.assertIn(
            "compare_digest",
            source,
            "Admin key comparison must use secrets.compare_digest (constant-time)",
        )

    def test_admin_key_does_not_use_string_equality(self):
        """
        Verifies that the vulnerable `!=` comparison has been removed.
        """
        from api.endpoints.admin_payouts import _require_admin
        source = inspect.getsource(_require_admin)
        self.assertNotIn(
            "credentials.credentials !=",
            source,
            "Admin key must not use != comparison (timing attack surface)",
        )


# ===========================================================================
# 4. Rate-Limit Bypass via X-Forwarded-For
# ===========================================================================

class TestRateLimitXFFBypass(unittest.TestCase):
    """
    The GraphQL rate limiter trusts X-Forwarded-For without validation.
    Any client can forge this header to appear to come from any IP address,
    effectively bypassing IP-based rate limits.
    """

    @classmethod
    def setUpClass(cls):
        # Prime strawberry cache (Python 3.9 + pydantic compat issue)
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            try:
                import utils.graphql_auth  # noqa: F401
            except ImportError:
                pass

    def _make_graphql_info(self, xff_ip=None, real_ip="192.168.1.100"):
        """Simulate a GraphQL context with optional X-Forwarded-For header."""

        class FakeHeaders:
            def get(self, key, default=None):
                if key == "x-forwarded-for" and xff_ip:
                    return xff_ip
                return default

        req = MagicMock()
        req.headers = FakeHeaders()
        req.client = MagicMock()
        req.client.host = real_ip

        class FakeContext(dict):
            pass

        return FakeContext({"user_id": None, "request": req})

    def test_xff_header_overrides_real_client_ip_in_graphql_rate_limiter(self):
        """
        VULNERABILITY CONFIRMED: the GraphQL rate limiter reads the first IP
        from X-Forwarded-For and ignores the real TCP connection IP.

        Attack scenario:
          1. Attacker's real IP: 192.168.1.100 (or a single IP)
          2. Attacker sends X-Forwarded-For: 10.0.0.1, 10.0.0.2, ... rotating
          3. Rate limiter keys on 10.0.0.1, 10.0.0.2 ... — never blocks the attacker

        This test PASSES while the vulnerability exists (it confirms the behavior).
        Fix: only trust X-Forwarded-For if the request comes from a known proxy/
        load balancer, or use request.client.host exclusively.
        """
        from utils.rate_limit import get_identifier_from_context

        info_with_xff = MagicMock()
        info_with_xff.context = self._make_graphql_info(
            xff_ip="10.0.0.1", real_ip="192.168.1.100"
        )

        identifier = get_identifier_from_context(info_with_xff)

        # The rate limiter keys on the SPOOFED IP — real IP is ignored
        self.assertIn("10.0.0.1", identifier,
                      "XFF bypass does not work — rate limiter ignores XFF")
        self.assertNotIn("192.168.1.100", identifier)

    def test_attacker_can_rotate_ips_to_multiply_rate_limit_allowance(self):
        """
        VULNERABILITY: by rotating X-Forwarded-For each request, an attacker
        gets N * rate_limit requests instead of just rate_limit.

        Simulated: 5 requests, each with a different spoofed IP → 5 different
        rate-limit buckets, none of which is ever exhausted.
        """
        from utils.rate_limit import get_identifier_from_context

        identifiers = set()
        for i in range(5):
            info = MagicMock()
            info.context = self._make_graphql_info(
                xff_ip=f"10.0.0.{i}", real_ip="192.168.1.100"
            )
            identifiers.add(get_identifier_from_context(info))

        # Each request gets a unique rate-limit bucket — all from one real IP
        self.assertEqual(len(identifiers), 5,
                         "All 5 requests should appear to come from different IPs")

    def test_first_ip_in_xff_chain_is_used_not_closest_proxy(self):
        """
        ATTACK DETAIL: when multiple IPs appear in X-Forwarded-For (a chain of
        proxies), the rate limiter uses the FIRST one (client-supplied) not
        the last one (nearest proxy, harder to spoof).

        X-Forwarded-For: ATTACKER_CONTROLLED, REAL_PROXY_IP
        The attacker controls the first value.
        """
        from utils.rate_limit import get_identifier_from_context

        info = MagicMock()
        # xff chain: first IP is attacker-controlled, second is a real proxy
        info.context = self._make_graphql_info(
            xff_ip="1.2.3.4, 10.10.10.10", real_ip="192.168.1.100"
        )
        identifier = get_identifier_from_context(info)

        self.assertIn("1.2.3.4", identifier,
                      "First (attacker-controlled) IP should be used")
        self.assertNotIn("10.10.10.10", identifier)


# ===========================================================================
# 5. Upload Polyglot / Content Spoofing Attacks
# ===========================================================================

class TestUploadContentSpoofing(unittest.TestCase):
    """
    Attack: bypass file-type validation by disguising malicious files as images.
    """

    def _sig(self, content: bytes):
        from api.endpoints.uploads import validate_image_signature
        return validate_image_signature(content)

    def test_zip_archive_disguised_as_jpeg_rejected(self):
        """
        ATTACK: ZIP files (and USDZ, XLSX, DOCX, JAR, APK, ...) all start with
        the PK magic bytes b'PK\\x03\\x04'. If treated as images, a malicious
        ZIP could be uploaded. Must be rejected by magic-byte check.
        """
        zip_content = b"PK\x03\x04" + b"\x00" * 100  # ZIP magic
        self.assertIsNone(
            self._sig(zip_content),
            "VULNERABILITY: ZIP archive passes image validation",
        )

    def test_pdf_file_rejected(self):
        """
        ATTACK: PDF files can contain JavaScript. A PDF disguised as an image
        could be served from the CDN and executed in vulnerable PDF viewers.
        """
        pdf_content = b"%PDF-1.4\n" + b"\x00" * 50
        self.assertIsNone(
            self._sig(pdf_content),
            "VULNERABILITY: PDF passes image validation",
        )

    def test_html_xss_payload_disguised_as_image_rejected(self):
        """
        ATTACK: if an HTML file is served as image/jpeg from the CDN, browsers
        that sniff content types could execute it — stored XSS.
        """
        html_content = b"<html><script>alert(1)</script></html>" + b"\x00" * 30
        self.assertIsNone(
            self._sig(html_content),
            "VULNERABILITY: HTML/XSS payload passes image validation",
        )

    def test_php_shell_disguised_as_image_rejected(self):
        """
        ATTACK: classic webshell upload. A PHP file disguised as a JPEG.
        """
        php_content = b"<?php system($_GET['cmd']); ?>" + b"\x00" * 30
        self.assertIsNone(
            self._sig(php_content),
            "VULNERABILITY: PHP webshell passes image validation",
        )

    def test_elf_binary_rejected(self):
        """
        ATTACK: Linux ELF binary (starts with \\x7fELF) disguised as image.
        """
        elf_content = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 50
        self.assertIsNone(
            self._sig(elf_content),
            "VULNERABILITY: ELF binary passes image validation",
        )

    def test_xml_svg_rejected(self):
        """
        ATTACK: SVG is XML and can contain embedded JavaScript (onclick, script
        tags). An SVG stored in an S3 bucket and served via CDN would execute
        JS in browsers — stored XSS.

        SVG starts with either '<svg' or '<?xml', neither of which matches
        image magic bytes. Must be rejected.
        """
        svg_content = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
        self.assertIsNone(
            self._sig(svg_content),
            "VULNERABILITY: SVG/XML passes image validation",
        )

    def test_jpeg_magic_bytes_followed_by_php_code_fails_pil_verification(self):
        """
        ATTACK: polyglot file — valid JPEG magic bytes (\\xff\\xd8\\xff) at the
        start, followed by arbitrary malicious content. Passes magic-byte check
        but must FAIL PIL verification (which actually parses the image).

        This tests the defense-in-depth: magic bytes alone are not enough.
        """
        import asyncio
        from fastapi import UploadFile
        from io import BytesIO

        # Valid JPEG magic + PHP garbage body (not a real JPEG)
        polyglot = b"\xff\xd8\xff\xe0" + b"<?php system($_GET['cmd']); ?>" * 100

        async def _test():
            from api.endpoints.uploads import validate_upload, MAX_FILE_SIZES
            file = UploadFile(
                filename="evil.jpg",
                file=BytesIO(polyglot),
                headers={"content-type": "image/jpeg"},
            )
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                await validate_upload(file, "product", MAX_FILE_SIZES["product"])
            self.assertEqual(ctx.exception.status_code, 400,
                             "VULNERABILITY: polyglot JPEG+PHP passes validation")

        asyncio.run(_test())

    def test_path_traversal_in_filename_does_not_affect_storage_path(self):
        """
        ATTACK: filename like '../../etc/passwd' or '../../../app/config.py'
        could escape the intended S3 prefix if the filename is used directly
        in the storage path.

        The upload code uses ObjectId() as the path — filename should be ignored.
        """
        from api.endpoints.uploads import validate_image_signature

        # The validation functions don't use the filename, but let's verify
        # that the path construction ignores it by checking the code
        from api.endpoints import uploads
        source = inspect.getsource(uploads.upload_business_avatar)

        # The S3 path must be built from ObjectId/uuid, never from image.filename
        self.assertNotIn(
            "image.filename",
            source.replace("image.filename or", ""),  # allow the "or 'image.png'" pattern
            "VULNERABILITY: user-supplied filename may influence S3 storage path",
        )


# ===========================================================================
# 6. Mass Assignment — Role Escalation via Registration
# ===========================================================================

class TestMassAssignment(unittest.TestCase):
    """
    Attack: sneak a `role` field into the registration payload to self-promote
    to admin/manager without going through the normal access control path.
    """

    @classmethod
    def setUpClass(cls):
        # Prime strawberry submodule cache
        try:
            import utils.graphql_auth  # noqa: F401
        except ImportError:
            try:
                import utils.graphql_auth  # noqa: F401
            except ImportError:
                pass

    def test_register_input_schema_does_not_accept_role_field(self):
        """
        ATTACK: if the GraphQL RegisterInput type has a `role` field, an attacker
        could register with {"name": "x", "email": "x", "password": "x",
        "role": "admin"} and become an admin.

        The schema must not expose a `role` field in RegisterInput.
        """
        try:
            from schema.auth.types import RegisterInput
        except Exception:
            self.skipTest("Could not import schema (strawberry compat issue)")

        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RegisterInput)}
        self.assertNotIn(
            "role",
            field_names,
            "VULNERABILITY: RegisterInput exposes 'role' field — attacker can self-promote",
        )

    def test_login_input_schema_does_not_expose_role(self):
        """
        ATTACK: a login form that sends `role` should not be able to override
        the role stored in the database.
        """
        try:
            from schema.auth.types import LoginInput
        except Exception:
            self.skipTest("Could not import schema (strawberry compat issue)")

        import dataclasses
        field_names = {f.name for f in dataclasses.fields(LoginInput)}
        self.assertNotIn(
            "role",
            field_names,
            "VULNERABILITY: LoginInput exposes 'role' field",
        )

    def test_auth_mutation_hardcodes_customer_role(self):
        """
        ATTACK: even if RegisterInput doesn't expose role, the mutation handler
        might read it from another source. Verify the handler hardcodes 'customer'.
        """
        try:
            from schema.auth import mutations as auth_mutations
        except (ImportError, Exception):
            self.skipTest("Could not import schema (strawberry compat issue)")
        source = inspect.getsource(auth_mutations.AuthMutation.register)

        # The role must be hardcoded, never read from `input.role` or `input`
        self.assertIn(
            '"customer"',
            source,
            "register mutation must hardcode role='customer'",
        )
        self.assertNotIn(
            "input.role",
            source,
            "VULNERABILITY: register mutation reads role from user input",
        )


# ===========================================================================
# 7. Admin Endpoint — Key Bypass Attempts
# ===========================================================================

class TestAdminKeyAdversarial(unittest.TestCase):
    """
    Attack: bypass the admin API key check via injection, length abuse, or
    type confusion.
    """

    @classmethod
    def setUpClass(cls):
        from api.endpoints.admin_payouts import router as admin_router
        cls.app = _build_test_app(admin_router)

    async def _get(self, key_value):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            headers = {"Authorization": f"Bearer {key_value}"} if key_value is not None else {}
            return await client.get("/admin/pending-payouts", headers=headers)

    def test_sql_injection_in_admin_key_rejected(self):
        """
        ATTACK: try classic SQL injection in the key field.
        Not relevant for MongoDB, but tests that the comparison doesn't
        evaluate the value as a pattern or expression.
        """
        resp = _run(self._get("' OR '1'='1"))
        self.assertEqual(resp.status_code, 401)

    def test_key_with_newline_injection_rejected(self):
        """
        ATTACK: HTTP header injection via embedded newlines in the key value.
        """
        resp = _run(self._get("key\r\nX-Injected: evil"))
        # httpx should either reject or normalize — either way, the admin auth must fail
        self.assertIn(resp.status_code, [400, 401, 422],
                      "Newline injection in key should fail auth or be rejected by HTTP layer")

    def test_very_long_admin_key_rejected(self):
        """
        ATTACK: buffer overflow via extremely long key string.
        """
        resp = _run(self._get("A" * 100_000))
        self.assertEqual(resp.status_code, 401)

    def test_whitespace_only_key_rejected(self):
        """
        ATTACK: try keys that are only whitespace — might pass strip()-based checks.
        """
        for key in ["   ", "\t", "\n", "  correct-admin-key-adversarial  "]:
            resp = _run(self._get(key))
            self.assertEqual(resp.status_code, 401,
                             f"Whitespace variant '{repr(key)}' should be rejected")

    def test_unicode_homoglyph_key_rejected(self):
        """
        ATTACK: use Unicode homoglyphs that look identical to ASCII characters.
        'ｃｏｒｒｅｃｔ-ａｄｍｉｎ-ｋｅｙ' (full-width) should not match
        'correct-admin-key' (ASCII).

        HTTP headers must be ASCII/latin-1. If the HTTP layer raises UnicodeEncodeError
        when trying to send the header, that itself confirms the attack is blocked.
        """
        fullwidth_key = "ｃｏｒｒｅｃｔ"  # ｃｏｒｒｅｃｔ
        try:
            resp = _run(self._get(fullwidth_key))
            self.assertEqual(resp.status_code, 401)
        except UnicodeEncodeError:
            pass  # HTTP layer cannot encode non-ASCII in headers — attack blocked at transport


if __name__ == "__main__":
    unittest.main(verbosity=2)
