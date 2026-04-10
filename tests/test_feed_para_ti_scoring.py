"""Focused tests for Para Ti feed scoring."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from services.feed_service import feed_service


@pytest.mark.asyncio
async def test_para_ti_prioritizes_affinity_and_filters_by_radius(monkeypatch):
    now = datetime.now(timezone.utc)

    product_affine = SimpleNamespace(
        id="p1",
        branchId="b1",
        categoryId="c1",
        availability=True,
        createdAt=now - timedelta(days=2),
    )
    product_popular = SimpleNamespace(
        id="p2",
        branchId="b2",
        categoryId="c2",
        availability=True,
        createdAt=now - timedelta(days=1),
    )
    product_unavailable = SimpleNamespace(
        id="p3",
        branchId="b1",
        categoryId="c1",
        availability=False,
        createdAt=now,
    )

    async def mock_get_user_searches(_user_id, limit=100):
        assert limit == 100
        return [
            SimpleNamespace(
                clickedItems=[
                    SimpleNamespace(
                        itemType="product",
                        itemId="p1",
                        clicks=[now - timedelta(days=1)],
                    )
                ]
            )
        ]

    async def mock_get_by_user(_user_id, item_type=None):
        if item_type == "favorite":
            return [
                SimpleNamespace(
                    productId="p1",
                    createdAt=now - timedelta(days=1),
                )
            ]
        return []

    async def mock_get_branch_likes(_user_id):
        return []

    async def mock_get_by_ids(product_ids):
        return [product_affine] if "p1" in product_ids else []

    async def mock_recent_search_activity(_days):
        return {"p2": {"clicks": 10, "unique_users": 5}}

    async def mock_recent_favorite_activity(item_type, _days):
        if item_type == "favorite":
            return {"p2": 4}
        if item_type == "cart":
            return {"p2": 3}
        return {}

    async def mock_score_products_by_branch(_products, _user_location, radius_km=None):
        assert radius_km == 5
        # p1 and p2 are inside radius, p3 is unavailable and should never be scored.
        return [
            SimpleNamespace(id="p1", score=0.8),
            SimpleNamespace(id="p2", score=0.9),
        ]

    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_searches",
        mock_get_user_searches,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_by_user",
        mock_get_by_user,
    )
    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_by_user",
        mock_get_branch_likes,
    )
    monkeypatch.setattr(
        "services.feed_service.products_repo.get_by_ids",
        mock_get_by_ids,
    )
    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_recent_activity",
        mock_recent_search_activity,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_recent_activity",
        mock_recent_favorite_activity,
    )
    monkeypatch.setattr(
        "services.feed_service.scoring_service.score_products_by_branch",
        mock_score_products_by_branch,
    )

    results = await feed_service.get_para_ti_section(
        user_id="u1",
        user_location=(-82.3, 23.1),
        branch_ids={"b1", "b2"},
        limit=5,
        radius_km=5,
        all_products=[product_affine, product_popular, product_unavailable],
    )

    assert [item.product.id for item in results] == ["p1", "p2"]
    assert all(item.product.id != "p3" for item in results)
    assert results[0].section_scores["category_affinity"] > 0
    assert results[0].section_scores["recent_intent"] > 0
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_te_podria_gustar_prioritizes_adjacent_affinity_without_repeating(monkeypatch):
    now = datetime.now(timezone.utc)

    interacted = SimpleNamespace(
        id="p1",
        branchId="b1",
        categoryId="c1",
        availability=True,
        createdAt=now - timedelta(days=3),
    )
    adjacent = SimpleNamespace(
        id="p2",
        branchId="b1",
        categoryId="c1",
        availability=True,
        createdAt=now - timedelta(days=1),
    )
    unrelated = SimpleNamespace(
        id="p3",
        branchId="b9",
        categoryId="c9",
        availability=True,
        createdAt=now - timedelta(days=1),
    )

    async def mock_get_user_searches(_user_id, limit=100):
        assert limit == 100
        return []

    async def mock_get_by_user(_user_id, item_type=None):
        if item_type == "favorite":
            return [
                SimpleNamespace(
                    productId="p1",
                    createdAt=now - timedelta(days=1),
                )
            ]
        return []

    async def mock_get_branch_likes(_user_id):
        return []

    async def mock_get_by_ids(product_ids):
        return [interacted] if "p1" in product_ids else []

    async def mock_recent_search_activity(_days):
        return {}

    async def mock_recent_favorite_activity(item_type, _days):
        if item_type == "favorite":
            return {"p2": 2}
        return {}

    async def mock_score_products_by_branch(_products, _user_location, radius_km=None):
        assert radius_km == 5
        return [
            SimpleNamespace(id="p1", score=0.9),
            SimpleNamespace(id="p2", score=0.8),
            SimpleNamespace(id="p3", score=0.7),
        ]

    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_searches",
        mock_get_user_searches,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_by_user",
        mock_get_by_user,
    )
    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_by_user",
        mock_get_branch_likes,
    )
    monkeypatch.setattr(
        "services.feed_service.products_repo.get_by_ids",
        mock_get_by_ids,
    )
    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_recent_activity",
        mock_recent_search_activity,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_recent_activity",
        mock_recent_favorite_activity,
    )
    monkeypatch.setattr(
        "services.feed_service.scoring_service.score_products_by_branch",
        mock_score_products_by_branch,
    )

    results = await feed_service.get_te_podria_gustar_section(
        user_id="u1",
        user_location=(-82.3, 23.1),
        branch_ids={"b1", "b9"},
        limit=5,
        radius_km=5,
        all_products=[interacted, adjacent, unrelated],
    )

    assert [item.product.id for item in results][:2] == ["p2", "p3"]
    assert all(item.product.id != "p1" for item in results)
    assert results[0].section_scores["category_affinity"] > 0
    assert results[0].score > results[1].score


def test_deduplicate_sections_backfills_with_next_unique_candidate():
    make_scored = lambda pid, score: SimpleNamespace(
        product=SimpleNamespace(id=pid),
        score=score,
        section_scores={},
    )

    sections = [
        [make_scored("a", 0.9), make_scored("b", 0.8), make_scored("c", 0.7)],
        [make_scored("a", 0.95), make_scored("d", 0.85), make_scored("e", 0.75)],
        [make_scored("b", 0.88), make_scored("f", 0.77)],
    ]

    deduped = feed_service._deduplicate_sections(sections, target_limit=2)

    assert [[item.product.id for item in section] for section in deduped] == [
        ["a", "b"],
        ["d", "e"],
        ["f"],
    ]


@pytest.mark.asyncio
async def test_basado_busquedas_prioritizes_search_affinity_over_global_popularity(
    monkeypatch,
):
    now = datetime.now(timezone.utc)

    searched = SimpleNamespace(
        id="p1",
        branchId="b1",
        categoryId="c1",
        availability=True,
        createdAt=now - timedelta(days=2),
    )
    adjacent = SimpleNamespace(
        id="p2",
        branchId="b1",
        categoryId="c1",
        availability=True,
        createdAt=now - timedelta(days=1),
    )
    global_only = SimpleNamespace(
        id="p3",
        branchId="b9",
        categoryId="c9",
        availability=True,
        createdAt=now - timedelta(days=1),
    )

    async def mock_search_click_preferences(_user_id):
        return {"p1": 1.0}

    async def mock_get_user_searches(_user_id, limit=100):
        assert limit == 100
        return []

    async def mock_get_by_user(_user_id, item_type=None):
        return []

    async def mock_get_branch_likes(_user_id):
        return []

    async def mock_get_by_ids(product_ids):
        return [searched] if "p1" in product_ids else []

    async def mock_recent_search_activity(_days):
        return {"p3": {"clicks": 8, "unique_users": 4}}

    async def mock_recent_favorite_activity(_item_type, _days):
        if _item_type == "favorite":
            return {"p3": 4}
        if _item_type == "cart":
            return {"p3": 4}
        return {}

    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_click_preferences",
        mock_search_click_preferences,
    )
    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_searches",
        mock_get_user_searches,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_by_user",
        mock_get_by_user,
    )
    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_by_user",
        mock_get_branch_likes,
    )
    monkeypatch.setattr(
        "services.feed_service.products_repo.get_by_ids",
        mock_get_by_ids,
    )
    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_recent_activity",
        mock_recent_search_activity,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_recent_activity",
        mock_recent_favorite_activity,
    )

    results = await feed_service.get_basado_busquedas_section(
        user_id="u1",
        branch_ids={"b1", "b9"},
        limit=5,
        all_products=[searched, adjacent, global_only],
    )

    assert [item.product.id for item in results][:2] == ["p1", "p2"]
    assert all(item.product.id != "p3" for item in results)
    assert results[0].section_scores["clicked_in_searches"] > 0
    assert results[1].section_scores["category_affinity"] > 0
