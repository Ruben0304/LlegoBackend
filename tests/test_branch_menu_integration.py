"""Real MongoDB checks. Opt in with MENU_TEST_MONGODB_URL pointing to localhost."""

import asyncio
import io
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image, ImageDraw, ImageFont
from pymongo.errors import DuplicateKeyError

from clients import mongodb_client
from repositories import branch_menus_repo
from services.menu_ocr_utils import build_index_fields
from services.menu_ocr_worker import process_pending_menus
from services.menu_search_service import search_menus

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def menu_db(monkeypatch):
    uri = os.environ.get("MENU_TEST_MONGODB_URL")
    if not uri:
        pytest.skip("MENU_TEST_MONGODB_URL not set; real MongoDB tests disabled")
    assert urlparse(uri).hostname in {"localhost", "127.0.0.1"}, "Only a local test MongoDB is allowed"
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    name = f"llego_menu_test_{uuid.uuid4().hex}"
    db = client[name]
    monkeypatch.setattr(mongodb_client, "database", db)
    monkeypatch.setattr(mongodb_client, "mongo_client", client)
    try:
        await client.admin.command("ping")
        await mongodb_client._create_branch_menu_indexes()
        indexes = await db.branch_menus.index_information()
        assert indexes["idx_branch_unique"]["unique"] is True
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def _indexed_menu(branch_id, text="Pizza Margarita"):
    menu, _ = await branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/menu.jpg")
    lines = [{"text": text, "conf": 0.95, "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}]
    index = build_index_fields(lines)
    assert await branch_menus_repo.set_ocr_result(str(menu.id), menu.image, lines, index["tokens"], index["trigrams"], {"verdict": "good"})
    return menu


async def test_replacement_resets_ocr_and_preserves_identity(menu_db):
    branch_id = str(ObjectId())
    old = await _indexed_menu(branch_id)
    new, previous = await branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/new.jpg")
    assert previous == old.image
    assert new.id == old.id
    assert new.createdAt == old.createdAt
    assert new.ocrStatus == "pending"
    assert new.lines == new.tokens == new.trigrams == []
    assert new.quality is None
    assert not await branch_menus_repo.set_ocr_result(str(old.id), old.image, [], [], [], {})
    assert not await branch_menus_repo.set_ocr_failed(str(old.id), old.image, "stale result")


async def test_unique_index_prevents_duplicate_branch_menus(menu_db):
    menu = await _indexed_menu(str(ObjectId()))
    document = (await menu_db.branch_menus.find_one({"_id": menu.id})).copy()
    document["_id"] = ObjectId()
    with pytest.raises(DuplicateKeyError):
        await menu_db.branch_menus.insert_one(document)


async def test_parallel_workers_claim_each_menu_once(menu_db):
    for _ in range(12):
        branch_id = str(ObjectId())
        await branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/menu.jpg")
    claimed = await asyncio.gather(*(branch_menus_repo.claim_next_pending() for _ in range(24)))
    ids = [menu.id for menu in claimed if menu]
    assert len(ids) == len(set(ids)) == 12
    assert await menu_db.branch_menus.count_documents({"ocrStatus": "processing"}) == 12


async def test_concurrent_first_uploads_create_one_document(menu_db):
    branch_id = str(ObjectId())
    results = await asyncio.gather(*(branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/{index}.jpg") for index in range(20)))
    assert len({menu.id for menu, _ in results}) == 1
    assert sum(previous is None for _, previous in results) == 1
    assert await menu_db.branch_menus.count_documents({"branchId": ObjectId(branch_id)}) == 1


async def test_concurrent_replacements_return_exact_previous_images(menu_db):
    branch_id = str(ObjectId())
    first, _ = await branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/first.jpg")
    images = [f"branch_menus/{branch_id}/{i}.jpg" for i in range(16)]
    results = await asyncio.gather(*(branch_menus_repo.upsert_image(branch_id, image) for image in images))
    current = await branch_menus_repo.get_by_branch(branch_id)
    previous = [old for _, old in results]
    assert len(set(previous)) == 16, "Concurrent swaps lost the previous image; S3 cleanup would leak files"
    assert set(previous) | {current.image} == {first.image, *images}
    assert await menu_db.branch_menus.count_documents({"branchId": ObjectId(branch_id)}) == 1


async def test_only_stale_processing_is_requeued(menu_db):
    old = await _indexed_menu(str(ObjectId()))
    fresh = await _indexed_menu(str(ObjectId()))
    for menu, age in [(old, 601), (fresh, 1)]:
        await menu_db.branch_menus.update_one({"_id": menu.id}, {"$set": {"ocrStatus": "processing", "processingStartedAt": datetime.utcnow() - timedelta(seconds=age)}})
    assert await branch_menus_repo.requeue_stale_processing(600) == 1
    assert (await branch_menus_repo.get_by_id(str(old.id))).ocrStatus == "pending"
    assert (await branch_menus_repo.get_by_id(str(fresh.id))).ocrStatus == "processing"


async def test_real_aggregation_filters_status_activity_scope_and_typo(menu_db):
    allowed = str(ObjectId())
    await _indexed_menu(allowed)
    inactive = await _indexed_menu(str(ObjectId()))
    await branch_menus_repo.set_active(str(inactive.branchId), False)
    pending, _ = await branch_menus_repo.upsert_image(str(ObjectId()), "branch_menus/pending.jpg")
    for query in ["pizza", "piza", "PÍZZA"]:
        results = await search_menus(query, branch_ids=[allowed, str(inactive.branchId), str(pending.branchId)])
        assert [str(row["menu"].branchId) for row in results] == [allowed]
    assert await search_menus("pizza", branch_ids=[]) == []
    assert await search_menus("sushi", branch_ids=[allowed]) == []


async def test_real_ocr_worker_persists_searchable_results(menu_db):
    pytest.importorskip("rapidocr_onnxruntime")
    image = Image.new("RGB", (1200, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=60)
    for index, text in enumerate(["PIZZA MARGARITA 8.50", "PASTA CARBONARA 9.00", "CAFE 2.00", "POLLO ASADO 12.00", "ARROZ 4.00"]):
        draw.text((40, 30 + index * 120), text, font=font, fill="black")
    content = io.BytesIO()
    image.save(content, format="PNG")
    branch_id = str(ObjectId())
    menu, _ = await branch_menus_repo.upsert_image(branch_id, f"branch_menus/{branch_id}/real.jpg")
    with patch("services.menu_ocr_service.fetch_image_bytes", AsyncMock(return_value=content.getvalue())):
        assert await process_pending_menus(batch_limit=1) == 1
    saved = await branch_menus_repo.get_by_id(str(menu.id))
    assert saved.ocrStatus == "done"
    assert saved.quality["verdict"] in {"good", "fair", "bad"}
    results = await search_menus("pizza", branch_ids=[branch_id])
    assert len(results) == 1
    polygon = results[0]["matches"][0]["polygon"]
    assert len(polygon) == 4
    assert all(0 <= coordinate <= 1 for point in polygon for coordinate in point)


async def test_fetch_failure_is_recorded_without_requeue(menu_db):
    failed, _ = await branch_menus_repo.upsert_image(str(ObjectId()), "branch_menus/broken.jpg")
    with patch("services.menu_ocr_service.fetch_image_bytes", AsyncMock(side_effect=RuntimeError("S3 unavailable"))):
        assert await process_pending_menus(batch_limit=1) == 0
    saved = await branch_menus_repo.get_by_id(str(failed.id))
    assert saved.ocrStatus == "failed"
    assert "S3 unavailable" in saved.ocrError
    assert saved.processingStartedAt is None
    assert await branch_menus_repo.claim_next_pending() is None


async def test_http_upload_graphql_permissions_search_toggle_and_delete(menu_db, monkeypatch):
    import httpx
    from main import app
    from utils.auth import create_access_token
    from utils.rate_limit import limiter

    owner, stranger, business, branch = (ObjectId() for _ in range(4))
    now = datetime.utcnow()
    await menu_db.bussisnes.insert_one({"_id": business, "ownerId": owner, "name": "Test menu business", "avatar": "", "globalRating": 0, "approvalStatus": "approved", "isActive": True, "createdAt": now})
    await menu_db.branches.insert_one({"_id": branch, "businessId": business, "name": "Menu branch", "coordinates": {"type": "Point", "coordinates": [-82.3, 23.1]}, "phone": "55555555", "schedule": {"days": []}, "managerIds": [], "tipos": ["restaurante"], "createdAt": now})
    token = create_access_token({"user_id": str(owner), "role": "customer"})
    stranger_token = create_access_token({"user_id": str(stranger), "role": "customer"})
    monkeypatch.setattr(limiter, "enabled", False)
    storage = {}
    s3 = MagicMock()
    s3.put_object.side_effect = lambda **kwargs: storage.update({kwargs["Key"]: kwargs["Body"]})
    s3.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(storage[kwargs["Key"]])}
    s3.delete_object.side_effect = lambda **kwargs: storage.pop(kwargs["Key"], None)
    s3.generate_presigned_url.return_value = "https://example.test/menu.jpg"
    image = Image.new("RGB", (900, 500), "white")
    ImageDraw.Draw(image).text((50, 100), "PIZZA MARGARITA 8.50", fill="black", font=ImageFont.load_default(size=60))
    content = io.BytesIO()
    image.save(content, format="PNG")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        async def gql(query, variables):
            response = await http.post("/graphql", json={"query": query, "variables": variables})
            assert response.status_code == 200, response.text
            return response.json()

        with patch("utils.s3.get_s3_client", return_value=s3), patch("services.menu_ocr_service.get_s3_client", return_value=s3):
            response = await http.post("/upload/branch-menu/image", data={"branch_id": str(branch)}, files={"image": ("menu.png", content.getvalue(), "image/png")})
            assert response.status_code == 401
            response = await http.post("/upload/branch-menu/image", headers={"Authorization": f"Bearer {stranger_token}"}, data={"branch_id": str(branch)}, files={"image": ("menu.png", content.getvalue(), "image/png")})
            assert response.status_code == 403
            response = await http.post("/upload/branch-menu/image", headers={"Authorization": f"Bearer {token}"}, data={"branch_id": str(branch)}, files={"image": ("menu.png", content.getvalue(), "image/png")})
            assert response.status_code == 200, response.text
            key = response.json()["image_path"]
            assert key.startswith(f"branch_menus/{branch}/")
            variables = {"b": str(branch), "i": key, "j": token}
            set_query = 'mutation($b: String!, $i: String!, $j: String!) { setBranchMenu(branchId: $b, image: $i, jwt: $j) { ocrStatus } }'
            denied = await gql(set_query, {**variables, "j": stranger_token})
            assert denied.get("errors")
            saved = await gql(set_query, variables)
            assert not saved.get("errors"), saved
            assert saved["data"]["setBranchMenu"]["ocrStatus"] == "pending"
            assert await process_pending_menus(batch_limit=1) == 1
            found = await gql('query { searchMenus(query: "pizza") { matchCount matches { polygon } branch { name } } }', {})
            assert not found.get("errors"), found
            assert len(found["data"]["searchMenus"]) == 1
            assert found["data"]["searchMenus"][0]["branch"]["name"] == "Menu branch"
            toggle = await gql('mutation($b: String!, $j: String!) { toggleBranchMenu(branchId: $b, isActive: false, jwt: $j) { isActive } }', {"b": str(branch), "j": token})
            assert not toggle.get("errors"), toggle
            assert toggle["data"]["toggleBranchMenu"]["isActive"] is False
            for jwt_value, visible in [(None, False), (token, True), (stranger_token, False)]:
                result = await gql('query($b: String!, $j: String) { branchMenu(branchId: $b, jwt: $j) { id } }', {"b": str(branch), "j": jwt_value})
                assert not result.get("errors"), result
                assert (result["data"]["branchMenu"] is not None) is visible
            hidden = await gql('query { searchMenus(query: "pizza") { matchCount } }', {})
            assert hidden["data"]["searchMenus"] == []
            deleted = await gql('mutation($b: String!, $j: String!) { deleteBranchMenu(branchId: $b, jwt: $j) }', {"b": str(branch), "j": token})
            assert not deleted.get("errors"), deleted
            assert deleted["data"]["deleteBranchMenu"] is True
            assert key not in storage
            assert await branch_menus_repo.get_by_branch(str(branch)) is None
