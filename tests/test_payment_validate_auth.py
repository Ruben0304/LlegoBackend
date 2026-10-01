"""POST /payments/validate: exige JWT y tiene rate limit por usuario.

Era publico y sin limite (context.md §12.6): cada llamada corre OCR con Gemini
y puede guardar un registro de pago.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

import api.routes as routes
from core.config import settings
from utils.auth import create_access_token
from utils.rate_limit import get_user_or_ip, limiter, rate_limit_exceeded_handler


@pytest.fixture(autouse=True)
def jwt_secret():
    with patch.object(settings, "jwt_secret", "test-jwt-secret-validate"):
        limiter.reset()
        yield
        limiter.reset()


@pytest.fixture
def ocr():
    result = SimpleNamespace(
        matched=True,
        message="ok",
        detected_transfer_id="TX1",
        extracted_data=SimpleNamespace(model_dump=lambda: {"numero_transferencia": "TX1"}),
        saved_payment=None,
    )
    mock = AsyncMock(return_value=result)
    with patch.object(routes, "validate_payment_image_with_transfer_id", mock):
        yield mock


@pytest.fixture
def client():
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(routes.router)
    return TestClient(app)


def _post(client, headers=None):
    return client.post(
        "/payments/validate",
        data={"transfer_id": "TX1"},
        files={"file": ("sms.jpg", b"\xff\xd8\xff" + b"\x00" * 32, "image/jpeg")},
        headers=headers or {},
    )


def _auth(user_id, scheme="bearer"):
    # La app iOS manda el token_type del login: "bearer" en minusculas.
    return {"Authorization": f"{scheme} {create_access_token({'user_id': user_id, 'role': 'customer'})}"}


def test_rejects_anonymous_requests_without_running_ocr(client, ocr):
    res = _post(client)

    assert res.status_code == 401
    ocr.assert_not_awaited()


def test_rejects_invalid_jwt(client, ocr):
    res = _post(client, {"Authorization": "Bearer not.a.jwt"})

    assert res.status_code == 401
    ocr.assert_not_awaited()


@pytest.mark.parametrize("scheme", ["bearer", "Bearer"])
def test_authenticated_user_can_validate(client, ocr, scheme):
    res = _post(client, _auth("user-ok", scheme))

    assert res.status_code == 200, res.text
    assert res.json()["matched"] is True
    ocr.assert_awaited_once()


def test_rate_limit_is_per_user(client, ocr):
    for _ in range(6):
        assert _post(client, _auth("user-busy")).status_code == 200

    blocked = _post(client, _auth("user-busy"))
    other_user = _post(client, _auth("user-calm"))

    assert blocked.status_code == 429
    assert other_user.status_code == 200
    assert ocr.await_count == 7


def _request(headers):
    request = MagicMock()
    request.headers = headers
    request.client = SimpleNamespace(host="10.0.0.1")
    return request


@pytest.mark.parametrize("scheme", ["bearer", "Bearer", "BEARER"])
def test_rate_limit_key_uses_user_for_any_bearer_casing(scheme):
    token = create_access_token({"user_id": "u-1", "role": "customer"})
    with patch("utils.rate_limit.get_remote_address", return_value="10.0.0.1"):
        key = get_user_or_ip(_request({"Authorization": f"{scheme} {token}"}))

    assert key == "user:u-1"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "bearer garbage"}, {"Authorization": "Basic abc"}])
def test_rate_limit_key_falls_back_to_ip(headers):
    with patch("utils.rate_limit.get_remote_address", return_value="10.0.0.1"):
        assert get_user_or_ip(_request(headers)) == "ip:10.0.0.1"
