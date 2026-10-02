"""Banners de plataforma (`platformBanners`): carrusel 16:9 del feed.

LlegoiOS (graphql/feed/GetPlatformBanners.graphql) y LlegoApk
(ProductFeedRepository.fetchPlatformBanners) ya piden `platformBanners`; antes
no existía y la query fallaba en validación. Estos tests fijan el contrato con
las dos apps, la lógica pura (acción al tocar, validaciones) y que gestionar
banners es solo para admins.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
import strawberry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from graphql import parse, validate

import api.endpoints.uploads as uploads
import schema.platform_banners.mutations as banner_mutations
import schema.platform_banners.queries as banner_queries
import schema.platform_banners.types as banner_types
from core.config import settings
from domain.platform_banners import PlatformBanner
from repositories.platform_banner_repository import active_banners_filter
from schema.platform_banners.inputs import CreatePlatformBannerInput, UpdatePlatformBannerInput
from schema.schema import schema as graphql_schema
from services.platform_banners import (
    banner_action_url,
    normalize_banner_link,
    normalize_banner_whatsapp,
    validate_app_target,
    validate_window,
    whatsapp_digits,
)
from utils.auth import create_access_token
from utils.rate_limit import limiter

BANNER_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"
ADMIN_ID = "507f1f77bcf86cd799439013"

# Copia literal de LlegoiOS/graphql/feed/GetPlatformBanners.graphql; LlegoApk
# (ProductFeedRepository.kt) manda la misma operación como texto.
CLIENT_OPERATION = """
query GetPlatformBanners {
  platformBanners(appTarget: "customer") {
    id
    imagePath
    imageUrl
    title
    actionUrl
    branchId
    order
  }
}
"""


@pytest.fixture(autouse=True)
def jwt_secret():
    with patch.object(settings, "jwt_secret", "test-jwt-secret-banners"):
        limiter.reset()
        yield


def _token(role: str, user_id: str = ADMIN_ID) -> str:
    return create_access_token({"user_id": user_id, "role": role})


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _banner(**overrides) -> PlatformBanner:
    data = {
        "_id": BANNER_ID,
        "imagePath": "platform_banners/x.jpg",
        "title": "Promo",
        "link": None,
        "whatsapp": None,
        "branchId": None,
        "appTarget": "customer",
        "order": 0,
        "isActive": True,
        "createdAt": datetime(2026, 10, 1),
    }
    data.update(overrides)
    return PlatformBanner(**data)


@pytest.fixture
def repo(monkeypatch):
    fake = SimpleNamespace(
        get_active=AsyncMock(return_value=[_banner()]),
        list_all=AsyncMock(return_value=[_banner()]),
        get_by_id=AsyncMock(return_value=_banner()),
        next_order=AsyncMock(return_value=3),
        create=AsyncMock(side_effect=lambda data: _banner(**{k: v for k, v in data.items() if k != "createdByUserId"})),
        update=AsyncMock(side_effect=lambda _id, updates: _banner(**updates)),
        delete=AsyncMock(return_value=True),
        reorder=AsyncMock(),
    )
    monkeypatch.setattr(banner_queries, "platform_banners_repo", fake)
    monkeypatch.setattr(banner_mutations, "platform_banners_repo", fake)
    monkeypatch.setattr(
        banner_mutations.branches_repo, "get_by_id", AsyncMock(return_value=SimpleNamespace(id=BRANCH_ID))
    )
    return fake


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- contrato con las apps


def test_client_operation_validates_against_schema():
    assert validate(graphql_schema._schema, parse(CLIENT_OPERATION)) == []


def test_public_query_returns_active_banners_with_urls(repo, monkeypatch):
    monkeypatch.setattr(banner_types, "get_public_url", lambda path: f"https://cdn/{path}")
    repo.get_active.return_value = [
        _banner(whatsapp="5555 5555", link="https://llego.cu", branchId=BRANCH_ID, order=2)
    ]

    result = run(banner_queries.PlatformBannerQuery().platform_banners(info=_info()))

    repo.get_active.assert_awaited_once_with("customer")
    banner = result[0]
    assert banner.image_url() == "https://cdn/platform_banners/x.jpg"
    # WhatsApp gana al link; el número cubano sale con el código 53.
    assert banner.action_url() == "https://wa.me/5355555555"
    assert banner.branchId == BRANCH_ID
    assert banner.order == 2


def test_public_query_unknown_app_target_returns_empty(repo):
    result = run(banner_queries.PlatformBannerQuery().platform_banners(info=_info(), appTarget="otra"))

    assert result == []
    repo.get_active.assert_not_awaited()


def test_active_filter_respects_publication_window():
    now = datetime(2026, 10, 2, 12, 0)
    query = active_banners_filter("customer", now)

    assert query["appTarget"] == "customer"
    assert query["isActive"] is True
    assert {"startAt": {"$lte": now}} in query["$and"][0]["$or"]
    assert {"endAt": {"$gt": now}} in query["$and"][1]["$or"]
    # Sin fechas el banner se muestra mientras esté activo.
    assert {"startAt": None} in query["$and"][0]["$or"]
    assert {"endAt": None} in query["$and"][1]["$or"]


# ---------------------------------------------------------------- lógica pura


def test_whatsapp_digits_normalizes_numbers():
    assert whatsapp_digits("55555555") == "5355555555"
    assert whatsapp_digits("+53 5555-5555") == "5355555555"
    assert whatsapp_digits("+1 (305) 555-1234") == "13055551234"
    assert whatsapp_digits("12") is None
    assert whatsapp_digits("") is None


def test_action_url_prefers_whatsapp_then_link():
    assert banner_action_url("55555555", "https://llego.cu") == "https://wa.me/5355555555"
    assert banner_action_url(None, " https://llego.cu ") == "https://llego.cu"
    assert banner_action_url(None, None) is None
    assert banner_action_url("abc", "") is None


def test_link_whatsapp_and_target_validation():
    assert normalize_banner_link("  ") is None
    assert normalize_banner_link("https://llego.cu/x") == "https://llego.cu/x"
    with pytest.raises(ValueError):
        normalize_banner_link("javascript:alert(1)")
    with pytest.raises(ValueError):
        normalize_banner_link("llego.cu")
    assert normalize_banner_whatsapp(None) is None
    with pytest.raises(ValueError):
        normalize_banner_whatsapp("llámame")
    assert validate_app_target("customer") == "customer"
    with pytest.raises(ValueError):
        validate_app_target("merchant")


def test_window_must_be_increasing_even_with_aware_dates():
    start = datetime(2026, 10, 1, 10, 0)
    validate_window(start, None)
    validate_window(start, start + timedelta(days=1))
    with pytest.raises(ValueError):
        validate_window(start, start)
    with pytest.raises(ValueError):
        # 10:00 en Cuba (UTC-4) son las 14:00 UTC: antes del inicio (15:00 UTC).
        validate_window(datetime(2026, 10, 1, 15, 0), datetime(2026, 10, 1, 10, 0, tzinfo=timezone(timedelta(hours=-4))))


# ---------------------------------------------------------------- solo admin


def _admin_calls(jwt):
    mutation = banner_mutations.PlatformBannerMutation()
    query = banner_queries.PlatformBannerQuery()
    return [
        mutation.create_platform_banner(info=_info(), input=CreatePlatformBannerInput(imagePath="p.jpg"), jwt=jwt),
        mutation.update_platform_banner(info=_info(), id=BANNER_ID, input=UpdatePlatformBannerInput(title="x"), jwt=jwt),
        mutation.set_platform_banner_active(info=_info(), id=BANNER_ID, isActive=False, jwt=jwt),
        mutation.reorder_platform_banners(info=_info(), ids=[BANNER_ID], jwt=jwt),
        mutation.delete_platform_banner(info=_info(), id=BANNER_ID, jwt=jwt),
        query.admin_platform_banners(info=_info(), jwt=jwt),
    ]


@pytest.mark.parametrize("role", ["customer", "manager", "risk_admin"])
def test_admin_operations_reject_other_roles(repo, role):
    for call in _admin_calls(_token(role)):
        with pytest.raises(Exception, match="Acceso denegado"):
            run(call)
    for method in ("create", "update", "delete", "reorder", "list_all"):
        getattr(repo, method).assert_not_awaited()


def test_admin_operations_reject_missing_jwt(repo):
    for call in _admin_calls(None):
        with pytest.raises(Exception, match="Autenticación requerida"):
            run(call)
    repo.create.assert_not_awaited()


# ---------------------------------------------------------------- crear / editar / ordenar / borrar


def test_create_appends_to_end_and_validates(repo):
    mutation = banner_mutations.PlatformBannerMutation()

    created = run(
        mutation.create_platform_banner(
            info=_info(),
            input=CreatePlatformBannerInput(
                imagePath=" platform_banners/a.jpg ",
                title="  ",
                link="https://llego.cu",
                branchId=BRANCH_ID,
            ),
            jwt=_token("admin"),
        )
    )

    data = repo.create.await_args.args[0]
    assert data["imagePath"] == "platform_banners/a.jpg"
    assert data["title"] is None
    assert data["order"] == 3  # next_order: al final del carrusel
    assert data["createdByUserId"] == ADMIN_ID
    assert created.branchId == BRANCH_ID

    with pytest.raises(Exception, match="URL http"):
        run(
            mutation.create_platform_banner(
                info=_info(),
                input=CreatePlatformBannerInput(imagePath="p.jpg", link="ftp://x"),
                jwt=_token("admin"),
            )
        )


def test_create_rejects_unknown_branch(repo, monkeypatch):
    monkeypatch.setattr(banner_mutations.branches_repo, "get_by_id", AsyncMock(return_value=None))

    with pytest.raises(Exception, match="tienda del banner no existe"):
        run(
            banner_mutations.PlatformBannerMutation().create_platform_banner(
                info=_info(),
                input=CreatePlatformBannerInput(imagePath="p.jpg", branchId=BRANCH_ID),
                jwt=_token("admin"),
            )
        )
    repo.create.assert_not_awaited()


def test_update_only_touches_sent_fields_and_null_clears(repo):
    repo.get_by_id.return_value = _banner(link="https://llego.cu", whatsapp="55555555")

    run(
        banner_mutations.PlatformBannerMutation().update_platform_banner(
            info=_info(),
            id=BANNER_ID,
            input=UpdatePlatformBannerInput(link=None, order=5),
            jwt=_token("admin"),
        )
    )

    updates = repo.update.await_args.args[1]
    assert updates == {"link": None, "order": 5}


def test_update_rejects_null_on_required_fields(repo):
    with pytest.raises(Exception, match="imagePath no puede ser null"):
        run(
            banner_mutations.PlatformBannerMutation().update_platform_banner(
                info=_info(), id=BANNER_ID, input=UpdatePlatformBannerInput(imagePath=None), jwt=_token("admin")
            )
        )
    repo.update.assert_not_awaited()


def test_update_checks_window_against_stored_dates(repo):
    repo.get_by_id.return_value = _banner(startAt=datetime(2026, 10, 10))

    with pytest.raises(Exception, match="posterior"):
        run(
            banner_mutations.PlatformBannerMutation().update_platform_banner(
                info=_info(),
                id=BANNER_ID,
                input=UpdatePlatformBannerInput(endAt=datetime(2026, 10, 5)),
                jwt=_token("admin"),
            )
        )


def test_update_input_defaults_are_unset():
    assert UpdatePlatformBannerInput().title is strawberry.UNSET


def test_set_active(repo):
    run(
        banner_mutations.PlatformBannerMutation().set_platform_banner_active(
            info=_info(), id=BANNER_ID, isActive=False, jwt=_token("admin")
        )
    )
    repo.update.assert_awaited_once_with(BANNER_ID, {"isActive": False})


def test_reorder_sets_positions_and_rejects_mixed_apps(repo):
    other = "507f1f77bcf86cd799439099"
    repo.get_by_id.side_effect = lambda banner_id: _banner(_id=banner_id)

    run(
        banner_mutations.PlatformBannerMutation().reorder_platform_banners(
            info=_info(), ids=[other, BANNER_ID], jwt=_token("admin")
        )
    )
    repo.reorder.assert_awaited_once_with([other, BANNER_ID])
    repo.list_all.assert_awaited_once_with("customer")

    repo.reorder.reset_mock()
    repo.get_by_id.side_effect = lambda banner_id: _banner(
        _id=banner_id, appTarget="business" if banner_id == other else "customer"
    )
    with pytest.raises(Exception, match="misma app"):
        run(
            banner_mutations.PlatformBannerMutation().reorder_platform_banners(
                info=_info(), ids=[other, BANNER_ID], jwt=_token("admin")
            )
        )
    with pytest.raises(Exception, match="repetidos"):
        run(
            banner_mutations.PlatformBannerMutation().reorder_platform_banners(
                info=_info(), ids=[BANNER_ID, BANNER_ID], jwt=_token("admin")
            )
        )
    repo.reorder.assert_not_awaited()


def test_delete_removes_image_best_effort(repo, monkeypatch):
    delete_file = AsyncMock(side_effect=RuntimeError("s3 caído"))
    monkeypatch.setattr(banner_mutations, "delete_file", delete_file)

    deleted = run(
        banner_mutations.PlatformBannerMutation().delete_platform_banner(
            info=_info(), id=BANNER_ID, jwt=_token("admin")
        )
    )

    assert deleted is True
    repo.delete.assert_awaited_once_with(BANNER_ID)
    delete_file.assert_awaited_once_with("platform_banners/x.jpg")


# ---------------------------------------------------------------- subida de la imagen


@pytest.fixture
def client():
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(uploads.router)
    return TestClient(app)


def _post_image(client, headers=None):
    files = {"image": ("b.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 64), "image/jpeg")}
    return client.post("/upload/platform-banner/image", files=files, headers=headers or {})


def test_upload_requires_admin(client):
    with patch.object(uploads, "upload_file", AsyncMock()) as upload:
        assert _post_image(client).status_code == 401
        assert _post_image(client, {"Authorization": f"Bearer {_token('customer', 'c-1')}"}).status_code == 403
    upload.assert_not_awaited()


def test_admin_can_upload_banner_image(client):
    with patch.object(uploads, "validate_upload", AsyncMock(return_value=b"img")), patch.object(
        uploads, "process_image_for_store_async", AsyncMock(return_value=(b"img", ".jpg"))
    ), patch.object(
        uploads, "upload_file", AsyncMock(return_value="platform_banners/x.jpg")
    ) as upload, patch.object(uploads, "generate_presigned_url", return_value="https://cdn/x.jpg"):
        res = _post_image(client, {"Authorization": f"Bearer {_token('admin', 'adm-banner')}"})

    assert res.status_code == 200, res.text
    assert res.json()["image_path"] == "platform_banners/x.jpg"
    assert upload.await_args.args[1] == "platform_banners"
