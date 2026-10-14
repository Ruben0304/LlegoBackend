"""IP del cliente para el rate limit (utils/client_ip.py).

El rate limit usaba el primer valor de X-Forwarded-For, que escribe el cliente:
rotándolo se saltaba el límite por IP. Ahora:
- Sin secreto de la web: X-Real-IP (la pone el edge de Railway) o la conexión.
- Con WEB_PROXY_SECRET y la cabecera X-Llego-Proxy-Secret correcta: la IP del
  navegador que reenvía la web (X-Llego-Client-IP, o X-Forwarded-For).
"""

import inspect
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from starlette.websockets import WebSocket

import utils.client_ip as client_ip
from core.config import settings
from utils.client_ip import get_client_ip, is_trusted_web_proxy
from utils.exception_handler import get_client_ip as error_log_client_ip
from utils.rate_limit import (
    get_identifier_from_context,
    get_user_or_ip,
    limiter,
    rate_limit_exceeded_handler,
)

SECRET = "secreto-compartido-con-la-web"
TCP_IP = "100.64.0.7"  # IP del proxy de Railway vista por uvicorn


def _scope(headers: dict, scope_type: str = "http") -> dict:
    return {
        "type": scope_type,
        "method": "POST",
        "path": "/graphql",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (TCP_IP, 51234),
        "query_string": b"",
    }


def _request(headers: dict) -> Request:
    """Request real de Starlette: cabeceras sin distinguir mayúsculas."""
    return Request(_scope(headers))


@pytest.fixture
def secret_configured():
    with patch.object(settings, "web_proxy_secret", SECRET):
        yield


@pytest.fixture
def no_secret():
    with patch.object(settings, "web_proxy_secret", ""):
        yield


# --- Sin secreto de la web ---------------------------------------------------


def test_spoofed_x_forwarded_for_is_ignored(no_secret):
    request = _request({"X-Forwarded-For": "1.2.3.4, 10.0.0.1"})

    assert get_client_ip(request) == TCP_IP


def test_uses_x_real_ip_set_by_railway_edge(no_secret):
    request = _request({"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "1.2.3.4"})

    assert get_client_ip(request) == "203.0.113.9"


def test_invalid_x_real_ip_falls_back_to_connection(no_secret):
    request = _request({"X-Real-IP": "no-es-una-ip"})

    assert get_client_ip(request) == TCP_IP


def test_forwarded_client_ip_is_ignored_when_no_secret_is_configured(no_secret):
    # Aunque alguien mande las cabeceras de la web (incluso con secreto vacío).
    request = _request(
        {
            "X-Llego-Proxy-Secret": "",
            "X-Llego-Client-IP": "1.2.3.4",
            "X-Forwarded-For": "1.2.3.4",
            "X-Real-IP": "203.0.113.9",
        }
    )

    assert not is_trusted_web_proxy(request)
    assert get_client_ip(request) == "203.0.113.9"


def test_missing_request_is_unknown():
    assert get_client_ip(None) == "unknown"


# --- Con secreto de la web ---------------------------------------------------


def test_web_proxy_with_valid_secret_forwards_browser_ip(secret_configured):
    request = _request(
        {
            "X-Llego-Proxy-Secret": SECRET,
            "X-Llego-Client-IP": "198.51.100.23",
            "X-Real-IP": "203.0.113.9",  # IP del servidor de la web
        }
    )

    assert is_trusted_web_proxy(request)
    assert get_client_ip(request) == "198.51.100.23"


def test_web_proxy_falls_back_to_x_forwarded_for_on_private_network(secret_configured):
    # Por la red privada de Railway no hay edge: llega el X-Forwarded-For de la web.
    request = _request({"X-Llego-Proxy-Secret": SECRET, "X-Forwarded-For": "198.51.100.23"})

    assert get_client_ip(request) == "198.51.100.23"


def test_web_proxy_ipv6_is_normalized(secret_configured):
    request = _request({"X-Llego-Proxy-Secret": SECRET, "X-Llego-Client-IP": " 2001:DB8::1 "})

    assert get_client_ip(request) == "2001:db8::1"


@pytest.mark.parametrize("wrong", ["otro-secreto", SECRET + "x", SECRET[:-1], " " + SECRET])
def test_wrong_secret_does_not_trust_forwarded_ip(secret_configured, wrong):
    request = _request(
        {
            "X-Llego-Proxy-Secret": wrong,
            "X-Llego-Client-IP": "1.2.3.4",
            "X-Forwarded-For": "1.2.3.4",
            "X-Real-IP": "203.0.113.9",
        }
    )

    assert not is_trusted_web_proxy(request)
    assert get_client_ip(request) == "203.0.113.9"


def test_valid_secret_with_garbage_ip_falls_back_to_edge_ip(secret_configured):
    request = _request(
        {
            "X-Llego-Proxy-Secret": SECRET,
            "X-Llego-Client-IP": "<script>",
            "X-Forwarded-For": "tampoco",
            "X-Real-IP": "203.0.113.9",
        }
    )

    assert get_client_ip(request) == "203.0.113.9"


def test_secret_is_compared_in_constant_time():
    source = inspect.getsource(client_ip.is_trusted_web_proxy)

    assert "compare_digest" in source
    assert "==" not in source


# --- Quién usa la IP ---------------------------------------------------------


def _info(request=None, websocket=None, user_id=None):
    context = {"user_id": user_id, "request": request, "websocket": websocket}
    return SimpleNamespace(context=context)


def test_graphql_identifier_prefers_user(no_secret):
    request = _request({"X-Forwarded-For": "1.2.3.4"})

    assert get_identifier_from_context(_info(request, user_id="u-1")) == "user:u-1"


def test_graphql_identifier_ignores_spoofed_xff(no_secret):
    identifiers = {
        get_identifier_from_context(_info(_request({"X-Forwarded-For": f"10.0.0.{i}"})))
        for i in range(5)
    }

    assert identifiers == {f"ip:{TCP_IP}"}


def test_graphql_identifier_uses_forwarded_ip_from_web(secret_configured):
    a = _request({"X-Llego-Proxy-Secret": SECRET, "X-Llego-Client-IP": "198.51.100.1"})
    b = _request({"X-Llego-Proxy-Secret": SECRET, "X-Llego-Client-IP": "198.51.100.2"})

    assert get_identifier_from_context(_info(a)) == "ip:198.51.100.1"
    assert get_identifier_from_context(_info(b)) == "ip:198.51.100.2"


def test_graphql_identifier_for_subscriptions_uses_websocket(no_secret):
    async def _noop(*_):
        return None

    websocket = WebSocket(_scope({"X-Real-IP": "203.0.113.9"}, "websocket"), _noop, _noop)

    assert get_identifier_from_context(_info(websocket=websocket)) == "ip:203.0.113.9"


def test_rest_key_ignores_spoofed_xff(no_secret):
    assert get_user_or_ip(_request({"X-Forwarded-For": "1.2.3.4"})) == f"ip:{TCP_IP}"


def test_error_log_ip_uses_same_rule(no_secret):
    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "203.0.113.9"})

    assert error_log_client_ip(request) == "203.0.113.9"


# --- Extremo a extremo con el limiter de slowapi ----------------------------


# Una sola app a nivel de módulo: slowapi registra el límite por nombre de
# función y, si se decorara en cada fixture, cada petición contaría doble.
_limited_app = FastAPI()
_limited_app.state.limiter = limiter
_limited_app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@_limited_app.get("/limitado")
@limiter.limit("2/minute")
async def limitado(request: Request):
    return {"ok": True}


@pytest.fixture
def limited_client():
    limiter.reset()
    yield TestClient(_limited_app)
    limiter.reset()


def test_rotating_xff_does_not_bypass_rest_limit(limited_client, no_secret):
    statuses = [
        limited_client.get("/limitado", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
        for i in range(4)
    ]

    assert statuses == [200, 200, 429, 429]


def test_web_proxy_clients_get_separate_buckets(limited_client, secret_configured):
    def call(ip):
        headers = {"X-Llego-Proxy-Secret": SECRET, "X-Llego-Client-IP": ip}
        return limited_client.get("/limitado", headers=headers).status_code

    assert [call("198.51.100.1") for _ in range(3)] == [200, 200, 429]
    # Otro navegador detrás de la misma web no comparte el cubo.
    assert call("198.51.100.2") == 200
