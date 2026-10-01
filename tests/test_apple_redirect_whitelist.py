"""Lista blanca de destinos del flujo web de Apple Sign-In (/apple/start).

/apple/callback redirige con ?token=JWT al destino guardado en el state, asi que
/apple/start solo puede aceptar los esquemas de las apps y las URL web exactas
de WEB_AUTH_CALLBACK_URLS. Antes aceptaba cualquier redirect_scheme y bastaba
redirect_scheme=https://atacante/x? para llevarse la sesion.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

from api.endpoints import apple_auth
from core.config import settings

WEB_CALLBACK = "https://llegoweb-production.up.railway.app/auth/callback"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(apple_auth.router)
    apple_auth._pending_states.clear()
    with patch.object(settings, "web_auth_callback_urls", WEB_CALLBACK):
        yield TestClient(app, follow_redirects=False)
    apple_auth._pending_states.clear()


def _stored_redirect(state: str) -> str:
    return apple_auth._pending_states[state]["redirect_uri"]


@pytest.mark.parametrize(
    "scheme,expected",
    [
        ("llego", "llego://auth/callback"),
        ("llegobusiness", "llegobusiness://auth/callback"),
        (WEB_CALLBACK, WEB_CALLBACK),
        (WEB_CALLBACK + "/", WEB_CALLBACK),
    ],
)
def test_start_accepts_whitelisted_destinations(client, scheme, expected):
    res = client.get("/apple/start", params={"redirect_scheme": scheme})

    assert res.status_code == 200, res.text
    assert _stored_redirect(res.json()["state"]) == expected


def test_start_without_scheme_keeps_customer_app_default(client):
    res = client.get("/apple/start")

    assert res.status_code == 200, res.text
    assert _stored_redirect(res.json()["state"]) == "llego://auth/callback"


@pytest.mark.parametrize(
    "scheme",
    [
        "https://atacante/x?",
        "https://atacante.com/auth/callback",
        "evil",
        "javascript",
        "",
        # Variantes que comparten prefijo con la URL permitida.
        WEB_CALLBACK + ".evil.com",
        WEB_CALLBACK + "?x=",
        "https://llegoweb-production.up.railway.app.evil.com/auth/callback",
        "http://llegoweb-production.up.railway.app/auth/callback",
    ],
)
def test_start_rejects_anything_else_without_creating_state(client, scheme):
    res = client.get("/apple/start", params={"redirect_scheme": scheme})

    assert res.status_code == 400
    assert apple_auth._pending_states == {}


def test_web_callback_list_is_configurable(client):
    other = "https://llego.example/auth/callback"
    with patch.object(settings, "web_auth_callback_urls", f"{WEB_CALLBACK}, {other}"):
        ok = client.get("/apple/start", params={"redirect_scheme": other})
    rejected = client.get("/apple/start", params={"redirect_scheme": other})

    assert ok.status_code == 200
    assert _stored_redirect(ok.json()["state"]) == other
    assert rejected.status_code == 400


def test_callback_redirects_token_to_the_whitelisted_web_url(client):
    state = client.get(
        "/apple/start", params={"redirect_scheme": WEB_CALLBACK}
    ).json()["state"]
    user = SimpleNamespace(id="user-1", email="a@b.c", role="customer")

    with patch.object(
        apple_auth, "verify_id_token", return_value={"sub": "apple-sub", "email": "a@b.c"}
    ), patch.object(
        apple_auth.auth_repo, "upsert_social_user", AsyncMock(return_value=user)
    ), patch.object(apple_auth, "create_access_token", return_value="jwt-123"):
        res = client.post(
            "/apple/callback", data={"state": state, "id_token": "tok", "code": "c"}
        )

    assert res.status_code == 303
    assert res.headers["location"] == f"{WEB_CALLBACK}?token=jwt-123"
    assert state not in apple_auth._pending_states


def test_callback_with_unknown_state_never_sends_a_token(client):
    res = client.post("/apple/callback", data={"state": "forged", "id_token": "tok"})

    assert res.status_code == 303
    assert res.headers["location"] == "llego://auth/callback?error=invalid_state"


def test_get_callback_error_redirects_to_default_deep_link(client):
    # Antes referenciaba ANDROID_DEEP_LINK (inexistente) y respondia 500.
    res = client.get("/apple/callback", params={"error": "user_cancelled_authorize"})

    assert res.status_code == 303
    assert res.headers["location"] == "llego://auth/callback?error=user_cancelled_authorize"
