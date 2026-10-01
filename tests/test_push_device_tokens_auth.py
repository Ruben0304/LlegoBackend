"""Endpoints REST de push y device tokens: los de ops exigen ADMIN_API_KEY.

Antes cualquiera podia listar los tokens (GET /api/device-tokens/), borrarlos
todos (DELETE /api/device-tokens/cleanup-invalid) o mandar una notificacion a
todos los dispositivos de una app (POST /api/push/clientes|negocios). Mismo
patron que /api/error-logs (context.md §12.3).
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

from api.endpoints import device_tokens, push_notifications
from core.config import settings
from repositories.device_token_repository import device_token_repo
from services.push_notification_service import push_service
from utils.auth import create_access_token

ADMIN_KEY = "test-admin-key-push"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_KEY}"}
PUSH_BODY = {"title": "Hola", "body": "Mundo"}

# (metodo, ruta, kwargs) de todo lo que debe ser solo para ops.
OPS_ENDPOINTS = [
    ("get", "/api/device-tokens/", {}),
    ("delete", "/api/device-tokens/cleanup-invalid", {}),
    ("post", "/api/push/clientes", {"json": PUSH_BODY}),
    ("post", "/api/push/negocios", {"json": PUSH_BODY}),
]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(device_tokens.router)
    app.include_router(push_notifications.router)
    with patch.object(settings, "admin_api_key", ADMIN_KEY), \
         patch.object(settings, "jwt_secret", "test-jwt-secret-push"):
        yield TestClient(app)


@pytest.fixture
def side_effects():
    """Todo lo que esos endpoints podrian leer, borrar o enviar."""
    db = MagicMock()
    db.__getitem__.return_value.count_documents = AsyncMock(return_value=3)
    db.__getitem__.return_value.delete_many = AsyncMock(
        return_value=SimpleNamespace(deleted_count=3)
    )
    tokens = [SimpleNamespace(
        id="t1", token="x" * 64, platform="IOS", appVersion="1.0", createdAt=None, userId=None
    )]
    get_all = AsyncMock(return_value=tokens)
    send = AsyncMock(return_value={"success": 1, "failed": 0, "failed_tokens": []})
    with patch("clients.get_database", return_value=db), \
         patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        yield SimpleNamespace(db=db, get_all=get_all, send=send)


def _assert_untouched(fx):
    fx.get_all.assert_not_awaited()
    fx.send.assert_not_awaited()
    fx.db.__getitem__.return_value.delete_many.assert_not_awaited()


@pytest.mark.parametrize("method,path,kwargs", OPS_ENDPOINTS)
def test_ops_endpoints_reject_missing_key(client, side_effects, method, path, kwargs):
    res = getattr(client, method)(path, **kwargs)

    assert res.status_code == 401
    _assert_untouched(side_effects)


@pytest.mark.parametrize("method,path,kwargs", OPS_ENDPOINTS)
def test_ops_endpoints_reject_wrong_key(client, side_effects, method, path, kwargs):
    res = getattr(client, method)(path, headers={"Authorization": "Bearer nope"}, **kwargs)

    assert res.status_code == 401
    _assert_untouched(side_effects)


@pytest.mark.parametrize("method,path,kwargs", OPS_ENDPOINTS)
def test_ops_endpoints_reject_admin_user_jwt(client, side_effects, method, path, kwargs):
    # Un JWT de usuario (aunque sea admin) no sustituye a la clave de ops.
    token = create_access_token({"user_id": "admin-1", "role": "admin"})
    res = getattr(client, method)(
        path, headers={"Authorization": f"Bearer {token}"}, **kwargs
    )

    assert res.status_code == 401
    _assert_untouched(side_effects)


@pytest.mark.parametrize("method,path,kwargs", OPS_ENDPOINTS)
def test_ops_endpoints_fail_closed_without_configured_key(client, side_effects, method, path, kwargs):
    with patch.object(settings, "admin_api_key", ""):
        res = getattr(client, method)(path, headers=ADMIN_HEADERS, **kwargs)

    assert res.status_code == 503
    _assert_untouched(side_effects)


def test_list_tokens_with_admin_key(client, side_effects):
    res = client.get("/api/device-tokens/", headers=ADMIN_HEADERS)

    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1


def test_cleanup_with_admin_key(client, side_effects):
    res = client.delete("/api/device-tokens/cleanup-invalid", headers=ADMIN_HEADERS)

    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 3


@pytest.mark.parametrize("path", ["/api/push/clientes", "/api/push/negocios"])
def test_push_with_admin_key(client, side_effects, path):
    res = client.post(path, json=PUSH_BODY, headers=ADMIN_HEADERS)

    assert res.status_code == 200, res.text
    side_effects.send.assert_awaited_once()


def test_register_and_unregister_stay_public(client):
    # Equivalentes REST de las mutations publicas registerDeviceToken /
    # unregisterDeviceToken: un dispositivo se registra antes del login.
    with patch.object(device_token_repo, "create_or_update", AsyncMock()) as create, \
         patch.object(device_token_repo, "deactivate", AsyncMock(return_value=True)) as deactivate:
        reg = client.post("/api/device-tokens/register", json={"token": "a" * 64})
        unreg = client.delete("/api/device-tokens/unregister", params={"token": "a" * 64})

    assert reg.status_code == 200, reg.text
    assert unreg.status_code == 200, unreg.text
    create.assert_awaited_once()
    deactivate.assert_awaited_once()
