"""Regression tests for the branch menu API: S3 key validation, search scope,
rate-limit call shape and the menu upload helper. No Mongo, S3 or network."""

import asyncio
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from PIL import Image

from domain.models import BranchMenu
from schema.schema import schema

BRANCH_ID = str(ObjectId())


def _fake_apply_jwt(jwt, info):
    info.context["user_id"] = "user-1"


def _menu(image: str) -> BranchMenu:
    now = datetime.utcnow()
    return BranchMenu(
        _id=ObjectId(), branchId=ObjectId(BRANCH_ID), image=image, createdAt=now, updatedAt=now
    )


def _run(query: str, variables: dict | None = None):
    return asyncio.run(
        schema.execute(query, variable_values=variables or {}, context_value={})
    )


SET_MENU = """
mutation($b: String!, $i: String!) {
  setBranchMenu(branchId: $b, image: $i) { ocrStatus branchId }
}
"""

SEARCH = """
query($q: String!, $t: String) {
  searchMenus(query: $q, branchTipo: $t) { matchCount }
}
"""


class TestSetBranchMenuImageKey:
    """`image` is client supplied and later deleted from S3: it must be a menu key."""

    @pytest.mark.parametrize(
        "bad_key",
        [
            "products/abc_123.jpg",  # another entity's file
            "showcases/abc_123.png",
            "branch_menus/../kyc/selfie.jpg",  # path traversal
            f"branch_menus/{ObjectId()}/image.jpg",  # another branch's menu
            f"branch_menus/{BRANCH_ID}/../image.jpg",
            "../etc/passwd",
            "   ",
        ],
    )
    def test_rejects_keys_outside_menu_folder(self, bad_key):
        with patch("schema.branch_menus.mutations.apply_optional_jwt", _fake_apply_jwt), patch(
            "schema.branch_menus.mutations.access_checker.require_branch_access", AsyncMock()
        ), patch(
            "schema.branch_menus.mutations.branch_menus_repo.upsert_image", AsyncMock()
        ) as upsert:
            result = _run(SET_MENU, {"b": BRANCH_ID, "i": bad_key})

        assert result.errors, "a key outside branch_menus/ must be rejected"
        upsert.assert_not_called()

    def test_accepts_menu_key_and_queues_ocr(self):
        key = f"branch_menus/{BRANCH_ID}/65f0c0c0c0c0c0c0c0c0c0c0_1700000000.jpg"
        with patch("schema.branch_menus.mutations.apply_optional_jwt", _fake_apply_jwt), patch(
            "schema.branch_menus.mutations.access_checker.require_branch_access", AsyncMock()
        ), patch(
            "schema.branch_menus.mutations.branch_menus_repo.upsert_image",
            AsyncMock(return_value=(_menu(key), None)),
        ) as upsert:
            result = _run(SET_MENU, {"b": BRANCH_ID, "i": key})

        assert not result.errors, result.errors
        assert result.data["setBranchMenu"]["ocrStatus"] == "pending"
        upsert.assert_awaited_once_with(BRANCH_ID, key)

    def test_unauthenticated_is_rejected_before_touching_the_repo(self):
        with patch("schema.branch_menus.mutations.apply_optional_jwt", lambda jwt, info: None), patch(
            "schema.branch_menus.mutations.branch_menus_repo.upsert_image", AsyncMock()
        ) as upsert:
            result = _run(SET_MENU, {"b": BRANCH_ID, "i": "branch_menus/x_1.jpg"})

        assert result.errors
        upsert.assert_not_called()


class TestSearchMenusScope:
    @pytest.mark.parametrize("first", [0, -1, -2147483648])
    def test_invalid_limit_rejected_before_database_lookup(self, first):
        with patch("schema.branch_menus.queries.rate_limit_graphql"), patch(
            "repositories.businesses_repo.get_ids_by_approval_status", AsyncMock()
        ) as lookup:
            result = _run(f'query {{ searchMenus(query: "pizza", first: {first}) {{ matchCount }} }}')
        assert result.errors
        assert "mayor que cero" in result.errors[0].message
        lookup.assert_not_awaited()

    def test_rate_limit_is_called_with_info_first(self):
        """rate_limit_graphql(info, limit_type): the arguments were once swapped."""
        limiter = MagicMock()
        with patch("schema.branch_menus.queries.apply_optional_jwt", lambda j, i: None), patch(
            "schema.branch_menus.queries.rate_limit_graphql", limiter
        ), patch(
            "repositories.businesses_repo.get_ids_by_approval_status", AsyncMock(return_value=[])
        ), patch(
            "repositories.branches_repo.get_ids_by_business_ids", AsyncMock(return_value=[])
        ), patch(
            "schema.branch_menus.queries.search_menus", AsyncMock(return_value=[])
        ):
            result = _run(SEARCH, {"q": "pizza"})

        assert not result.errors, result.errors
        info_arg, limit_type = limiter.call_args.args
        assert limit_type == "menu_search"
        assert not isinstance(info_arg, str)

    def test_menu_search_limit_type_exists(self):
        from utils.rate_limit import RATE_LIMITS

        assert "menu_search" in RATE_LIMITS

    def test_without_tipo_only_approved_businesses_are_searched(self):
        approved_branches = [str(ObjectId()), str(ObjectId())]
        service = AsyncMock(return_value=[])
        with patch("schema.branch_menus.queries.apply_optional_jwt", lambda j, i: None), patch(
            "schema.branch_menus.queries.rate_limit_graphql", MagicMock()
        ), patch(
            "repositories.businesses_repo.get_ids_by_approval_status",
            AsyncMock(return_value=["biz-1"]),
        ) as approved, patch(
            "repositories.branches_repo.get_ids_by_business_ids",
            AsyncMock(return_value=approved_branches),
        ), patch("schema.branch_menus.queries.search_menus", service):
            result = _run(SEARCH, {"q": "pizza"})

        assert not result.errors, result.errors
        approved.assert_awaited_once_with("approved")
        assert service.await_args.kwargs["branch_ids"] == approved_branches

    def test_no_approved_businesses_means_empty_scope_not_global_search(self):
        """An empty approved list must search nothing, never fall back to `None` (= all)."""
        service = AsyncMock(return_value=[])
        with patch("schema.branch_menus.queries.apply_optional_jwt", lambda j, i: None), patch(
            "schema.branch_menus.queries.rate_limit_graphql", MagicMock()
        ), patch(
            "repositories.businesses_repo.get_ids_by_approval_status", AsyncMock(return_value=[])
        ), patch(
            "repositories.branches_repo.get_ids_by_business_ids", AsyncMock(return_value=[])
        ), patch("schema.branch_menus.queries.search_menus", service):
            _run(SEARCH, {"q": "pizza"})

        assert service.await_args.kwargs["branch_ids"] == []

    def test_tipo_lookup_failure_propagates_instead_of_widening_the_search(self):
        service = AsyncMock(return_value=[])
        with patch("schema.branch_menus.queries.apply_optional_jwt", lambda j, i: None), patch(
            "schema.branch_menus.queries.rate_limit_graphql", MagicMock()
        ), patch(
            "services.feed_service.feed_service.get_branch_ids_by_tipo",
            AsyncMock(side_effect=RuntimeError("db down")),
        ), patch("schema.branch_menus.queries.search_menus", service):
            result = _run(SEARCH, {"q": "pizza", "t": "restaurante"})

        assert result.errors
        service.assert_not_called()


class TestMenuUploadHelper:
    @staticmethod
    def _png(size: tuple[int, int]) -> bytes:
        buf = BytesIO()
        Image.new("RGB", size, "white").save(buf, format="PNG")
        return buf.getvalue()

    def test_keeps_resolution_above_the_product_photo_limit(self):
        """Product photos are cut to 1440x1800; menus must keep their small print."""
        from api.endpoints.uploads import _prepare_menu_image

        out = Image.open(BytesIO(_prepare_menu_image(self._png((2000, 1500)))))
        assert out.size == (2000, 1500)
        assert out.format == "JPEG"

    def test_caps_very_large_photos(self):
        from api.endpoints.uploads import MENU_IMAGE_MAX_SIDE, _prepare_menu_image

        out = Image.open(BytesIO(_prepare_menu_image(self._png((4000, 3000)))))
        assert max(out.size) == MENU_IMAGE_MAX_SIDE

    def test_rejects_non_image_bytes(self):
        from api.endpoints.uploads import _prepare_menu_image

        with pytest.raises(Exception):
            _prepare_menu_image(b"not an image")


class TestMenuImageOwnership:
    @pytest.mark.parametrize("operation", ["replace", "delete"])
    @pytest.mark.parametrize("owned", [True, False])
    def test_cleanup_never_deletes_another_branch_image(self, operation, owned):
        old_image = f"branch_menus/{BRANCH_ID if owned else ObjectId()}/old.jpg"
        new_image = f"branch_menus/{BRANCH_ID}/new.jpg"
        with patch("schema.branch_menus.mutations.apply_optional_jwt", _fake_apply_jwt), patch(
            "schema.branch_menus.mutations.access_checker.require_branch_access", AsyncMock()
        ), patch(
            "schema.branch_menus.mutations.branch_menus_repo.upsert_image",
            AsyncMock(return_value=(_menu(new_image), old_image)),
        ), patch(
            "schema.branch_menus.mutations.branch_menus_repo.delete_by_branch",
            AsyncMock(return_value=_menu(old_image)),
        ), patch("schema.branch_menus.mutations.delete_file", AsyncMock()) as delete:
            if operation == "replace":
                result = _run(SET_MENU, {"b": BRANCH_ID, "i": new_image})
            else:
                result = _run('mutation($b: String!) { deleteBranchMenu(branchId: $b) }', {"b": BRANCH_ID})
        assert not result.errors, result.errors
        if owned:
            delete.assert_awaited_once_with(old_image)
        else:
            delete.assert_not_awaited()


@pytest.fixture
def menu_upload_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.endpoints.uploads import router, limiter, get_current_user_id_from_header

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id_from_header] = lambda: "user-1"
    monkeypatch.setattr(limiter, "enabled", False)
    with TestClient(app) as client:
        yield client


class TestMenuUploadEndpoint:
    def test_upload_checks_access_and_scopes_key(self, menu_upload_client):
        image = TestMenuUploadHelper._png((100, 100))
        key = f"branch_menus/{BRANCH_ID}/image.jpg"
        with patch("services.access_checker.access_checker.check_branch_access", AsyncMock(return_value=(True, None))) as access, patch(
            "api.endpoints.uploads.upload_file", AsyncMock(return_value=key)
        ) as upload, patch("api.endpoints.uploads.generate_presigned_url", return_value="https://example.test/image.jpg"):
            response = menu_upload_client.post("/upload/branch-menu/image", data={"branch_id": BRANCH_ID}, files={"image": ("menu.png", image, "image/png")})
        assert response.status_code == 200, response.text
        assert response.json()["image_path"] == key
        access.assert_awaited_once_with("user-1", BRANCH_ID)
        assert upload.await_args.args[1] == f"branch_menus/{BRANCH_ID}"
        assert upload.await_args.kwargs["generate_thumbnails"] is False

    @pytest.mark.parametrize("branch_id, status", [("invalid", 400), (BRANCH_ID, 403)])
    def test_rejects_invalid_or_unauthorized_branch_before_upload(self, menu_upload_client, branch_id, status):
        with patch("services.access_checker.access_checker.check_branch_access", AsyncMock(return_value=(False, "No autorizado"))), patch(
            "api.endpoints.uploads.upload_file", AsyncMock()
        ) as upload:
            response = menu_upload_client.post("/upload/branch-menu/image", data={"branch_id": branch_id}, files={"image": ("menu.png", b"fake", "image/png")})
        assert response.status_code == status
        upload.assert_not_awaited()

    def test_rejects_spoofed_image_before_s3(self, menu_upload_client):
        with patch("services.access_checker.access_checker.check_branch_access", AsyncMock(return_value=(True, None))), patch(
            "api.endpoints.uploads.upload_file", AsyncMock()
        ) as upload:
            response = menu_upload_client.post("/upload/branch-menu/image", data={"branch_id": BRANCH_ID}, files={"image": ("menu.png", b"fake", "image/png")})
        assert response.status_code == 400
        upload.assert_not_awaited()
