"""Vídeos promocionales: crear/editar/borrar/activar y subir sus vídeos y
miniaturas es solo para admins (context.md §12.10).

Antes cualquier usuario autenticado podía hacerlo (TODO explícito en
schema/promotional_videos/mutations.py y en api/endpoints/uploads.py), el mismo
agujero que tenían los tutoriales (§12.9).
"""

import asyncio
import os
from io import BytesIO
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

import api.endpoints.uploads as uploads
import schema.promotional_videos.mutations as promo_mutations
from core.config import settings
from utils.auth import create_access_token
from utils.rate_limit import limiter

VIDEO_ID = "507f1f77bcf86cd799439011"


@pytest.fixture(autouse=True)
def jwt_secret():
    with patch.object(settings, "jwt_secret", "test-jwt-secret-promo-videos"):
        limiter.reset()
        yield


def _token(role: str, user_id: str = "user-1") -> str:
    return create_access_token({"user_id": user_id, "role": role})


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _mutation_calls(mutation):
    """Coroutine factories de las 4 mutations, sin input real."""
    return [
        lambda jwt: mutation.create_promotional_video(info=_info(), input=None, jwt=jwt),
        lambda jwt: mutation.update_promotional_video(info=_info(), id=VIDEO_ID, input=None, jwt=jwt),
        lambda jwt: mutation.delete_promotional_video(info=_info(), id=VIDEO_ID, jwt=jwt),
        lambda jwt: mutation.toggle_promotional_video_active(info=_info(), id=VIDEO_ID, jwt=jwt),
    ]


@pytest.fixture
def repo(monkeypatch):
    fake = SimpleNamespace(
        create=AsyncMock(),
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=VIDEO_ID)),
        update=AsyncMock(),
        delete=AsyncMock(return_value=True),
        toggle_active=AsyncMock(),
    )
    monkeypatch.setattr(promo_mutations, "promotional_videos_repo", fake)
    return fake


@pytest.mark.parametrize("role", ["customer", "manager", "risk_admin"])
def test_mutations_reject_non_admin_roles(repo, role):
    mutation = promo_mutations.PromotionalVideoMutation()
    for call in _mutation_calls(mutation):
        with pytest.raises(Exception, match="Acceso denegado"):
            asyncio.run(call(_token(role)))
    for method in ("create", "get_by_id", "update", "delete", "toggle_active"):
        getattr(repo, method).assert_not_awaited()


def test_mutations_reject_missing_jwt(repo):
    mutation = promo_mutations.PromotionalVideoMutation()
    for call in _mutation_calls(mutation):
        with pytest.raises(Exception, match="Autenticación requerida"):
            asyncio.run(call(None))
    repo.delete.assert_not_awaited()


def test_admin_can_delete_promotional_video(repo):
    mutation = promo_mutations.PromotionalVideoMutation()

    deleted = asyncio.run(
        mutation.delete_promotional_video(info=_info(), id=VIDEO_ID, jwt=_token("admin"))
    )

    assert deleted is True
    repo.delete.assert_awaited_once_with(VIDEO_ID)


# ---------------------------------------------------------------- REST uploads


@pytest.fixture
def client():
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(uploads.router)
    return TestClient(app)


def _post_video(client, headers=None):
    files = {"video": ("p.mp4", BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64), "video/mp4")}
    return client.post("/upload/promotion/video", files=files, headers=headers or {})


def _post_thumbnail(client, headers=None):
    files = {"image": ("p.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 64), "image/jpeg")}
    return client.post("/upload/promotion/thumbnail", files=files, headers=headers or {})


@pytest.mark.parametrize("post", [_post_video, _post_thumbnail])
def test_upload_without_jwt_returns_401(client, post):
    with patch.object(uploads, "upload_file", AsyncMock()) as upload:
        res = post(client)

    assert res.status_code == 401
    upload.assert_not_awaited()


@pytest.mark.parametrize("post", [_post_video, _post_thumbnail])
def test_upload_with_customer_jwt_returns_403(client, post):
    with patch.object(uploads, "upload_file", AsyncMock()) as upload:
        res = post(client, {"Authorization": f"Bearer {_token('customer', 'cust-promo-403')}"})

    assert res.status_code == 403
    upload.assert_not_awaited()


def test_admin_can_upload_promotion_video(client):
    with patch.object(
        uploads, "validate_video_upload", AsyncMock(return_value=(b"vid", ".mp4"))
    ), patch.object(
        uploads, "upload_file", AsyncMock(return_value="promotions/videos/x.mp4")
    ) as upload, patch.object(
        uploads, "generate_presigned_url", return_value="https://cdn/x.mp4"
    ):
        res = _post_video(client, {"Authorization": f"Bearer {_token('admin', 'adm-promo-video')}"})

    assert res.status_code == 200, res.text
    assert res.json()["video_path"] == "promotions/videos/x.mp4"
    upload.assert_awaited_once()


def test_admin_can_upload_promotion_thumbnail(client):
    with patch.object(
        uploads, "validate_upload", AsyncMock(return_value=b"img")
    ), patch.object(
        uploads,
        "process_image_for_store_async",
        AsyncMock(return_value=(b"img", ".jpg")),
    ), patch.object(
        uploads, "upload_file", AsyncMock(return_value="promotions/thumbnails/x.jpg")
    ), patch.object(
        uploads, "generate_presigned_url", return_value="https://cdn/x.jpg"
    ):
        res = _post_thumbnail(client, {"Authorization": f"Bearer {_token('admin', 'adm-promo-thumb')}"})

    assert res.status_code == 200, res.text
    assert res.json()["thumbnail_path"] == "promotions/thumbnails/x.jpg"
