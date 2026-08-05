"""Performance tests for the feed service — response times and efficiency.

All tests mock external dependencies (repos, scoring service) with in-memory
data so measurements reflect only the algorithm cost, not I/O.

Thresholds:
  - Small dataset  (  50 products): < 50 ms per section
  - Medium dataset ( 200 products): < 100 ms per section
  - Large dataset  (1000 products): < 300 ms per section
  - Full parallel feed (all 10 sections, 1000 products): < 500 ms
  - _deduplicate_sections (10 sections × 200 products): < 20 ms
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from services.feed_service import ScoredFeedProduct, feed_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now()  # offset-naive — matches product_repository.calculate_freshness_scores


def make_products(n: int) -> list:
    """Generate n synthetic product objects covering a variety of branches/categories."""
    return [
        SimpleNamespace(
            id=f"p{i}",
            branchId=f"b{i % 20}",
            categoryId=f"c{i % 10}",
            availability=i % 5 != 0,  # ~80 % available
            createdAt=NOW - timedelta(days=i % 30),
        )
        for i in range(n)
    ]


def make_branch_ids(products: list) -> set:
    return {p.branchId for p in products}


def make_scored(product, score: float = 0.5) -> ScoredFeedProduct:
    return ScoredFeedProduct(product=product, score=score, section_scores={})


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


# ---------------------------------------------------------------------------
# Common monkeypatches (applied per-test via fixture or inline)
# ---------------------------------------------------------------------------

def patch_empty_repos(monkeypatch):
    """Patch all repo calls to return empty results (no user affinity data)."""

    async def no_searches(_user_id, limit=100):
        return []

    async def no_by_user(_user_id, item_type=None):
        return []

    async def no_branch_likes(_user_id):
        return []

    async def no_by_ids(_ids):
        return []

    async def no_recent_search(_days):
        return {}

    async def no_recent_fav(_item_type, _days):
        return {}

    async def no_orders(_user_id, status=None, limit=50, offset=0):
        return [], 0

    async def no_click_prefs(_user_id):
        return {}

    monkeypatch.setattr("services.feed_service.searches_repo.get_user_searches", no_searches)
    monkeypatch.setattr("services.feed_service.searches_repo.get_recent_activity", no_recent_search)
    monkeypatch.setattr("services.feed_service.searches_repo.get_user_click_preferences", no_click_prefs)
    monkeypatch.setattr("services.feed_service.favorites_cart_repo.get_by_user", no_by_user)
    monkeypatch.setattr("services.feed_service.favorites_cart_repo.get_recent_activity", no_recent_fav)
    monkeypatch.setattr("services.feed_service.branch_likes_repo.get_by_user", no_branch_likes)
    monkeypatch.setattr("services.feed_service.products_repo.get_by_ids", no_by_ids)
    monkeypatch.setattr("services.feed_service.orders_repo.get_by_customer", no_orders)


def patch_proximity(monkeypatch, products: list):
    """Return all available products with a fixed proximity score."""

    async def mock_score(_products, _location, radius_km=None):
        return [
            SimpleNamespace(id=p.id, score=0.5)
            for p in _products
            if p.availability
        ]

    monkeypatch.setattr(
        "services.feed_service.scoring_service.score_products_by_branch",
        mock_score,
    )


# ---------------------------------------------------------------------------
# Para Ti — personalized section
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_para_ti_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    start = time.perf_counter()
    results = await feed_service.get_para_ti_section(
        user_id="u1",
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"para_ti with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Populares Cerca
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_populares_cerca_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    async def mock_popularity(item_type):
        return {p.id: 0.6 for p in products[: n_products // 2]}

    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_popularity_scores",
        mock_popularity,
    )

    start = time.perf_counter()
    results = await feed_service.get_populares_cerca_section(
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"populares_cerca with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Trending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_trending_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    start = time.perf_counter()
    results = await feed_service.get_trending_section(
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"trending with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Mas Favoriteados
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_mas_favoriteados_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    async def mock_popularity(item_type):
        return {p.id: 0.7 for p in products[: n_products // 3]}

    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_popularity_scores",
        mock_popularity,
    )

    start = time.perf_counter()
    results = await feed_service.get_mas_favoriteados_section(
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"mas_favoriteados with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Cerca de Ti
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_cerca_ti_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    async def mock_popularity(item_type):
        return {}

    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_popularity_scores",
        mock_popularity,
    )

    start = time.perf_counter()
    results = await feed_service.get_cerca_de_ti_section(
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"cerca_ti with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Basado en Busquedas
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_basado_busquedas_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)

    # Simulate user click preference on first 10 % of products
    click_prefs = {p.id: 1.0 for p in products[: max(1, n_products // 10)]}

    async def mock_click_prefs(_user_id):
        return click_prefs

    async def mock_by_ids(ids):
        ids_set = set(ids)
        return [p for p in products if p.id in ids_set]

    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_click_preferences",
        mock_click_prefs,
    )
    monkeypatch.setattr("services.feed_service.products_repo.get_by_ids", mock_by_ids)

    start = time.perf_counter()
    results = await feed_service.get_basado_busquedas_section(
        user_id="u1",
        branch_ids=make_branch_ids(products),
        limit=10,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"basado_busquedas with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Hora del Dia
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_hora_del_dia_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    start = time.perf_counter()
    results = await feed_service.get_hora_del_dia_section(
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"hora_del_dia with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Pide de Nuevo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_pide_de_nuevo_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    # Simulate order history referencing some products
    order_products = products[: max(1, n_products // 5)]

    async def mock_get_orders(_user_id, status=None, limit=50, offset=0):
        orders = [
            SimpleNamespace(
                items=[
                    SimpleNamespace(itemType="product", itemId=p.id, quantity=1)
                    for p in order_products[:3]
                ],
                createdAt=NOW - timedelta(days=i + 1),
                completedAt=NOW - timedelta(days=i + 1),
            )
            for i in range(min(5, len(order_products)))
        ]
        return orders, len(orders)

    async def mock_by_ids(ids):
        ids_set = set(ids)
        return [p for p in products if p.id in ids_set]

    monkeypatch.setattr("services.feed_service.orders_repo.get_by_customer", mock_get_orders)
    monkeypatch.setattr("services.feed_service.products_repo.get_by_ids", mock_by_ids)

    start = time.perf_counter()
    results = await feed_service.get_pide_de_nuevo_section(
        user_id="u1",
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"pide_de_nuevo with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Te Podria Gustar
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_te_podria_gustar_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    start = time.perf_counter()
    results = await feed_service.get_te_podria_gustar_section(
        user_id="u1",
        user_location=(-82.3, 23.1),
        branch_ids=make_branch_ids(products),
        limit=10,
        radius_km=10.0,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"te_podria_gustar with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Nuevos Lugares Favoritos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(50, 50), (200, 100), (1000, 300)],
    ids=["small", "medium", "large"],
)
async def test_nuevos_lugares_favoritos_performance(monkeypatch, n_products, threshold_ms):
    products = make_products(n_products)
    patch_empty_repos(monkeypatch)

    # User likes first 5 branches (return branch IDs as strings, matching service expectation)
    liked_branch_ids = [f"b{i}" for i in range(5)]

    async def mock_get_user_preferences(_user_id):
        return liked_branch_ids

    async def mock_branch_popularity():
        return {f"b{i}": 0.7 for i in range(5)}

    async def mock_popularity(item_type):
        return {p.id: 0.5 for p in products[: n_products // 4]}

    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_user_preferences",
        mock_get_user_preferences,
    )
    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_popularity_scores",
        mock_branch_popularity,
    )
    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_popularity_scores",
        mock_popularity,
    )

    start = time.perf_counter()
    results = await feed_service.get_nuevos_lugares_favoritos_section(
        user_id="u1",
        branch_ids=make_branch_ids(products),
        limit=10,
        all_products=products,
    )
    ms = elapsed_ms(start)

    assert isinstance(results, list)
    assert ms < threshold_ms, (
        f"nuevos_lugares_favoritos with {n_products} products took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# _deduplicate_sections — pure CPU, no I/O
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "n_sections, n_products_each, threshold_ms",
    [
        (10, 50, 5),
        (10, 200, 20),
        (10, 500, 50),
    ],
    ids=["small", "medium", "large"],
)
def test_deduplicate_sections_performance(n_sections, n_products_each, threshold_ms):
    """_deduplicate_sections must stay fast even with many sections and many products each."""
    products = make_products(n_sections * n_products_each)
    # Build sections with overlapping products (worst case for dedup)
    sections = []
    for s in range(n_sections):
        offset = s * (n_products_each // 2)
        section_products = products[offset : offset + n_products_each]
        sections.append([make_scored(p, score=0.9 - s * 0.05) for p in section_products])

    start = time.perf_counter()
    result = feed_service._deduplicate_sections(sections, target_limit=10)
    ms = elapsed_ms(start)

    assert len(result) == n_sections
    assert ms < threshold_ms, (
        f"_deduplicate_sections ({n_sections} sections × {n_products_each} products) "
        f"took {ms:.1f} ms (limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Full parallel feed — all sections concurrently (simulates real get_feed call)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_products, threshold_ms",
    [(200, 300), (1000, 500)],
    ids=["medium", "large"],
)
async def test_full_parallel_feed_performance(monkeypatch, n_products, threshold_ms):
    """Runs all independent sections in parallel (mirrors asyncio.gather in get_feed)."""
    products = make_products(n_products)
    branch_ids = make_branch_ids(products)
    user_location = (-82.3, 23.1)

    patch_empty_repos(monkeypatch)
    patch_proximity(monkeypatch, products)

    async def mock_popularity(item_type):
        return {p.id: 0.5 for p in products[: n_products // 4]}

    monkeypatch.setattr(
        "services.feed_service.favorites_cart_repo.get_popularity_scores",
        mock_popularity,
    )

    async def mock_click_prefs(_user_id):
        return {}

    async def mock_branch_likes(_user_id):
        return []

    monkeypatch.setattr(
        "services.feed_service.searches_repo.get_user_click_preferences", mock_click_prefs
    )
    monkeypatch.setattr(
        "services.feed_service.branch_likes_repo.get_by_user", mock_branch_likes
    )

    async def mock_orders(_user_id, status=None, limit=50, offset=0):
        return [], 0

    monkeypatch.setattr("services.feed_service.orders_repo.get_by_customer", mock_orders)

    start = time.perf_counter()
    results = await asyncio.gather(
        feed_service.get_para_ti_section("u1", user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_populares_cerca_section(user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_trending_section(user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_mas_favoriteados_section(user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_cerca_de_ti_section(user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_basado_busquedas_section("u1", branch_ids, 10, all_products=products),
        feed_service.get_hora_del_dia_section(user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_pide_de_nuevo_section("u1", user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_te_podria_gustar_section("u1", user_location, branch_ids, 10, radius_km=10.0, all_products=products),
        feed_service.get_nuevos_lugares_favoritos_section("u1", branch_ids, 10, all_products=products),
        return_exceptions=True,
    )
    ms = elapsed_ms(start)

    # Ensure no section threw unexpectedly
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, f"Sections raised exceptions: {errors}"

    assert ms < threshold_ms, (
        f"Full parallel feed ({n_products} products, 10 sections) took {ms:.1f} ms "
        f"(limit {threshold_ms} ms)"
    )


# ---------------------------------------------------------------------------
# Scaling test — verify O(n) growth is reasonable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trending_scales_linearly(monkeypatch):
    """Score growth from 200→1000 products must be < 10× (linear, not quadratic)."""
    sizes = [200, 1000]
    times = []

    for n in sizes:
        products = make_products(n)
        patch_empty_repos(monkeypatch)
        patch_proximity(monkeypatch, products)

        start = time.perf_counter()
        await feed_service.get_trending_section(
            user_location=(-82.3, 23.1),
            branch_ids=make_branch_ids(products),
            limit=10,
            radius_km=10.0,
            all_products=products,
        )
        times.append(elapsed_ms(start))

    ratio = times[1] / times[0] if times[0] > 0 else 0
    assert ratio < 10, (
        f"trending time scaled {ratio:.1f}× from {sizes[0]} to {sizes[1]} products "
        f"({times[0]:.1f} ms → {times[1]:.1f} ms); suspected worse-than-linear growth"
    )
