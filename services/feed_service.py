"""Feed service for personalized product recommendations."""

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from domain.orders import OrderStatus
from repositories import (
    branch_likes_repo,
    branches_repo,
    businesses_repo,
    favorites_cart_repo,
    orders_repo,
    products_repo,
    searches_repo,
)
from services.scoring_service import scoring_service
from utils.cache import mem_cache


@dataclass
class ScoredFeedProduct:
    """Product with scoring breakdown for feed sections."""

    product: Any
    score: float
    section_scores: Dict[str, float]  # Desglose de scores por factor


class FeedService:
    """
    Service for generating personalized product feed with multiple sections.

    8 Sections:
    1. Para Ti (Personalizado)
    2. Populares Cerca de Ti
    3. Trending Ahora
    4. Basado en tus Búsquedas
    5. Nuevos en tus Lugares Favoritos
    6. Los Más Favoriteados
    7. Cerca de Ti
    8. Te Podría Gustar
    """

    # --- Section 1: Para Ti ---
    PARA_TI_CATEGORY_AFFINITY = 0.35
    PARA_TI_BRANCH_AFFINITY = 0.20
    PARA_TI_RECENT_INTENT = 0.20
    PARA_TI_PROXIMITY = 0.15
    PARA_TI_RECENT_POPULARITY = 0.10

    # --- Section 2: Populares Cerca ---
    POPULARES_POPULARITY = 0.50
    POPULARES_PROXIMITY = 0.40
    POPULARES_FRESHNESS = 0.10

    # --- Section 3: Trending ---
    TRENDING_CLICKS = 0.40
    TRENDING_FAVORITES = 0.30
    TRENDING_CART = 0.20
    TRENDING_PROXIMITY = 0.10

    # --- Section 4: Basado en Búsquedas ---
    BUSQUEDAS_SEARCH_INTENT = 0.45
    BUSQUEDAS_CATEGORY_AFFINITY = 0.25
    BUSQUEDAS_BRANCH_AFFINITY = 0.20
    BUSQUEDAS_RECENT_POPULARITY = 0.10

    # --- Section 5: Nuevos en Lugares Favoritos ---
    NUEVOS_BRANCH_AFFINITY = 0.50
    NUEVOS_FRESHNESS = 0.30
    NUEVOS_POPULARITY = 0.20

    # --- Section 6: Más Favoriteados ---
    FAVORITEADOS_FAVORITES = 0.60
    FAVORITEADOS_CART = 0.25
    FAVORITEADOS_PROXIMITY = 0.15

    # --- Section 7: Cerca de Ti ---
    CERCA_PROXIMITY = 0.70
    CERCA_AVAILABILITY = 0.20
    CERCA_POPULARITY = 0.10

    # --- Section 8: Te Podría Gustar ---
    GUSTAR_CATEGORY_AFFINITY = 0.40
    GUSTAR_BRANCH_AFFINITY = 0.20
    GUSTAR_NOVELTY = 0.15
    GUSTAR_PROXIMITY = 0.15
    GUSTAR_RECENT_POPULARITY = 0.10

    # --- Section: Pide de Nuevo ---
    PIDE_NUEVO_RECENCY = 0.55
    PIDE_NUEVO_FREQUENCY = 0.35
    PIDE_NUEVO_PROXIMITY = 0.10

    # --- Section: Hora del Día ---
    HORA_DIA_RECENT_POPULARITY = 0.60
    HORA_DIA_PROXIMITY = 0.30
    HORA_DIA_FRESHNESS = 0.10

    @staticmethod
    def get_meal_context() -> tuple[str, str]:
        """Return a situational section title/description based on time of day and day of week."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6

        if 7 <= hour < 12:
            if is_weekend:
                return "Desayunos del Finde", "Para arrancar bien el fin de semana"
            return "Desayunos Populares", "Los más pedidos para el desayuno"
        elif 12 <= hour < 16:
            if is_weekend:
                return "El Almuerzo del Finde", "Los más pedidos los fines de semana"
            return "Para el Almuerzo", "Los favoritos a la hora del almuerzo"
        elif 16 <= hour < 20:
            return "Para Merendar", "Lo más popular para la merienda"
        elif 20 <= hour < 24:
            return "Para la Cena", "Los más pedidos en la noche"
        else:
            return "Antojos de Noche", "Para los que no se duermen con hambre"

    async def get_branch_ids_by_tipo(self, branch_tipo: str) -> Set[str]:
        """Fetch branch IDs filtered by tipo, restricted to approved businesses."""
        cache_key = f"feed:branch_ids:{branch_tipo}"
        cached = mem_cache.get(cache_key)
        if cached is not None:
            return cached
        approved_business_ids = await businesses_repo.get_ids_by_approval_status("approved")
        ids = await branches_repo.get_ids_by_tipo(branch_tipo.lower(), business_ids=approved_business_ids)
        result = set(ids)
        mem_cache.set(cache_key, result, ttl=300)
        return result

    def _normalize_score_map(self, raw_scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize a score dictionary into the 0-1 range."""
        if not raw_scores:
            return {}

        positive_scores = {key: value for key, value in raw_scores.items() if value > 0}
        if not positive_scores:
            return {}

        max_value = max(positive_scores.values())
        if max_value <= 0:
            return {}

        return {key: min(value / max_value, 1.0) for key, value in positive_scores.items()}

    def _candidate_limit(self, limit: int) -> int:
        """Fetch extra candidates so later deduplication can backfill sections."""
        return max(limit * 3, 30)

    def _decay_factor(
        self, timestamp: Optional[datetime], half_life_days: float = 30.0
    ) -> float:
        """Apply an exponential time decay so recent actions weigh more."""
        if not timestamp:
            return 0.0

        if getattr(timestamp, "tzinfo", None) is not None:
            now = datetime.now(timestamp.tzinfo)
        else:
            now = datetime.now(timezone.utc).replace(tzinfo=None)

        age_seconds = max((now - timestamp).total_seconds(), 0.0)
        half_life_seconds = max(half_life_days * 86400, 1.0)
        return math.exp(-math.log(2) * (age_seconds / half_life_seconds))

    def _sort_scored_products(
        self, scored_products: List[ScoredFeedProduct]
    ) -> List[ScoredFeedProduct]:
        """Sort scored products with stable tie-breakers for more realistic ranking."""

        def sort_key(item: ScoredFeedProduct) -> tuple:
            created_at = getattr(item.product, "createdAt", None)
            created_ts = created_at.timestamp() if created_at else 0.0
            return (
                item.score,
                item.section_scores.get("recent_intent", 0.0),
                item.section_scores.get("category_affinity", 0.0),
                item.section_scores.get("branch_affinity", 0.0),
                item.section_scores.get("proximity", 0.0),
                item.section_scores.get("recent_popularity", 0.0),
                item.section_scores.get("freshness", 0.0),
                created_ts,
            )

        scored_products.sort(key=sort_key, reverse=True)
        return scored_products

    async def _prepare_products_with_proximity(
        self,
        products: List[Any],
        user_location: Optional[tuple],
        radius_km: Optional[float] = None,
    ) -> tuple[List[Any], Dict[str, float]]:
        """Build a proximity map and optionally trim items outside the requested radius."""
        if not products or not user_location:
            return products, {}

        scored_items = await scoring_service.score_products_by_branch(
            products,
            user_location,
            radius_km=radius_km,
        )
        proximity_map = {item.id: item.score for item in scored_items}

        if radius_km is not None:
            products = [product for product in products if str(product.id) in proximity_map]

        return products, proximity_map

    async def _build_recent_popularity_scores(
        self, days: int = 30
    ) -> Dict[str, float]:
        """Build recent popularity scores from clicks, favorites, and cart activity."""
        cache_key = f"feed:popularity_scores:{days}"
        cached = mem_cache.get(cache_key)
        if cached is not None:
            return cached

        recent_clicks_data, recent_favorites, recent_cart = await asyncio.gather(
            searches_repo.get_recent_activity(days),
            favorites_cart_repo.get_recent_activity("favorite", days),
            favorites_cart_repo.get_recent_activity("cart", days),
        )

        raw_scores: Dict[str, float] = {}

        for pid, data in recent_clicks_data.items():
            click_signal = data.get("clicks", 0) * 0.7 + data.get("unique_users", 0) * 0.3
            raw_scores[str(pid)] = raw_scores.get(str(pid), 0.0) + click_signal

        for pid, count in recent_favorites.items():
            raw_scores[str(pid)] = raw_scores.get(str(pid), 0.0) + count * 1.2

        for pid, count in recent_cart.items():
            raw_scores[str(pid)] = raw_scores.get(str(pid), 0.0) + count * 1.4

        result = self._normalize_score_map(raw_scores)
        mem_cache.set(cache_key, result, ttl=120)
        return result

    async def _build_para_ti_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Build lightweight affinity maps and direct interaction sets for feed ranking."""
        (
            searches,
            favorite_items,
            cart_items,
            liked_branches,
            (delivered_orders, _),
        ) = await asyncio.gather(
            searches_repo.get_user_searches(user_id, limit=100),
            favorites_cart_repo.get_by_user(user_id, "favorite"),
            favorites_cart_repo.get_by_user(user_id, "cart"),
            branch_likes_repo.get_by_user(user_id),
            orders_repo.get_by_customer(user_id, status=OrderStatus.DELIVERED, limit=50),
        )

        interacted_product_ids: Set[str] = set()
        for search in searches:
            for clicked_item in search.clickedItems:
                if clicked_item.itemType == "product":
                    interacted_product_ids.add(str(clicked_item.itemId))

        favorite_product_ids = {str(item.productId) for item in favorite_items}
        cart_product_ids = {str(item.productId) for item in cart_items}

        interacted_product_ids.update(favorite_product_ids)
        interacted_product_ids.update(cart_product_ids)

        interacted_products = (
            await products_repo.get_by_ids(sorted(interacted_product_ids))
            if interacted_product_ids
            else []
        )
        products_by_id = {str(product.id): product for product in interacted_products}

        product_intent_raw: Dict[str, float] = {}
        category_affinity_raw: Dict[str, float] = {}
        branch_affinity_raw: Dict[str, float] = {}

        def add_product_signal(product_id: Any, weight: float) -> None:
            pid = str(product_id)
            product_intent_raw[pid] = product_intent_raw.get(pid, 0.0) + weight

            product = products_by_id.get(pid)
            if not product:
                return

            if getattr(product, "categoryId", None):
                category_id = str(product.categoryId)
                category_affinity_raw[category_id] = (
                    category_affinity_raw.get(category_id, 0.0) + weight
                )

            branch_id = str(product.branchId)
            branch_affinity_raw[branch_id] = branch_affinity_raw.get(branch_id, 0.0) + weight

        for search in searches:
            for clicked_item in search.clickedItems:
                if clicked_item.itemType != "product":
                    continue
                for click_time in clicked_item.clicks:
                    add_product_signal(
                        clicked_item.itemId,
                        1.0 * self._decay_factor(click_time, half_life_days=14.0),
                    )

        for favorite_item in favorite_items:
            add_product_signal(
                favorite_item.productId,
                2.0
                * self._decay_factor(
                    getattr(favorite_item, "createdAt", None), half_life_days=30.0
                ),
            )

        for cart_item in cart_items:
            add_product_signal(
                cart_item.productId,
                2.4
                * self._decay_factor(
                    getattr(cart_item, "createdAt", None), half_life_days=21.0
                ),
            )

        for branch_like in liked_branches:
            branch_id = str(branch_like.branchId)
            branch_affinity_raw[branch_id] = branch_affinity_raw.get(branch_id, 0.0) + (
                1.6
                * self._decay_factor(
                    getattr(branch_like, "createdAt", None), half_life_days=45.0
                )
            )

        # Completed orders are the strongest purchase signal (weight 3.5, 60-day half-life)
        for order in delivered_orders:
            order_time = getattr(order, "completedAt", None) or getattr(order, "createdAt", None)
            for item in order.items:
                if item.itemType != "product":
                    continue
                add_product_signal(
                    item.itemId,
                    3.5 * self._decay_factor(order_time, half_life_days=60.0),
                )

        return {
            "product_intent": self._normalize_score_map(product_intent_raw),
            "category_affinity": self._normalize_score_map(category_affinity_raw),
            "branch_affinity": self._normalize_score_map(branch_affinity_raw),
            "favorite_products": favorite_product_ids,
            "cart_products": cart_product_ids,
        }

    async def get_para_ti_section(
        self,
        user_id: str,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 1: Para Ti (Personalizado)
        category affinity (35%) + branch affinity (20%) + recent intent (20%)
        + proximity (15%) + recent popularity (10%)
        """
        products = [
            p
            for p in (all_products or [])
            if str(p.branchId) in branch_ids and getattr(p, "availability", False)
        ]
        if not products:
            return []

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        user_profile, recent_popularity_scores = await asyncio.gather(
            self._build_para_ti_user_profile(user_id),
            self._build_recent_popularity_scores(days=30),
        )

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)
            category_id = str(product.categoryId) if getattr(product, "categoryId", None) else None

            category_affinity = (
                user_profile["category_affinity"].get(category_id, 0.0)
                if category_id
                else 0.0
            )
            branch_affinity = user_profile["branch_affinity"].get(str(product.branchId), 0.0)
            recent_intent = user_profile["product_intent"].get(pid, 0.0)
            proximity = proximity_map.get(pid, 0.0)
            recent_popularity = recent_popularity_scores.get(pid, 0.0)

            # Final score
            final_score = (
                category_affinity * self.PARA_TI_CATEGORY_AFFINITY
                + branch_affinity * self.PARA_TI_BRANCH_AFFINITY
                + recent_intent * self.PARA_TI_RECENT_INTENT
                + proximity * self.PARA_TI_PROXIMITY
                + recent_popularity * self.PARA_TI_RECENT_POPULARITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "category_affinity": category_affinity,
                        "branch_affinity": branch_affinity,
                        "recent_intent": recent_intent,
                        "proximity": proximity,
                        "recent_popularity": recent_popularity,
                    },
                )
            )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_populares_cerca_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 2: Populares Cerca de Ti
        popularity (50%) + proximity (40%) + freshness (10%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get signals in parallel
        popularity_favorites, popularity_cart = await asyncio.gather(
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        freshness_scores = products_repo.calculate_freshness_scores(products)

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            # Popularity
            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Proximity
            proximity = proximity_map.get(pid, 0.0)

            # Freshness
            freshness = freshness_scores.get(pid, 0.0)

            # Final score
            final_score = (
                popularity * self.POPULARES_POPULARITY
                + proximity * self.POPULARES_PROXIMITY
                + freshness * self.POPULARES_FRESHNESS
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "popularity": popularity,
                        "proximity": proximity,
                        "freshness": freshness,
                    },
                )
            )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_trending_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        days: int = 7,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 3: Trending Ahora
        recent_clicks (40%) + recent_favorites (30%) + recent_cart (20%) + proximity (10%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get recent activity in parallel
        recent_clicks_data, recent_favorites, recent_cart = await asyncio.gather(
            searches_repo.get_recent_activity(days),
            favorites_cart_repo.get_recent_activity("favorite", days),
            favorites_cart_repo.get_recent_activity("cart", days),
        )

        # Normalize recent clicks
        recent_clicks = {}
        if recent_clicks_data:
            max_clicks = max(data["clicks"] for data in recent_clicks_data.values())
            if max_clicks > 0:
                recent_clicks = {
                    pid: data["clicks"] / max_clicks
                    for pid, data in recent_clicks_data.items()
                }

        # Normalize recent favorites
        if recent_favorites:
            max_fav = max(recent_favorites.values())
            if max_fav > 0:
                recent_favorites = {
                    pid: count / max_fav for pid, count in recent_favorites.items()
                }

        # Normalize recent cart
        if recent_cart:
            max_cart = max(recent_cart.values())
            if max_cart > 0:
                recent_cart = {
                    pid: count / max_cart for pid, count in recent_cart.items()
                }

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            clicks = recent_clicks.get(pid, 0.0)
            favorites = recent_favorites.get(pid, 0.0)
            cart = recent_cart.get(pid, 0.0)
            proximity = proximity_map.get(pid, 0.0)

            # Final score
            final_score = (
                clicks * self.TRENDING_CLICKS
                + favorites * self.TRENDING_FAVORITES
                + cart * self.TRENDING_CART
                + proximity * self.TRENDING_PROXIMITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "recent_clicks": clicks,
                        "recent_favorites": favorites,
                        "recent_cart": cart,
                        "proximity": proximity,
                    },
                )
            )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_basado_busquedas_section(
        self,
        user_id: str,
        branch_ids: Set[str],
        limit: int = 10,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 4: Basado en tus Búsquedas
        search intent (45%) + category affinity (25%) + branch affinity (20%)
        + recent popularity (10%)
        """
        products = [
            p
            for p in (all_products or [])
            if str(p.branchId) in branch_ids and getattr(p, "availability", False)
        ]
        if not products:
            return []

        search_clicks, user_profile, recent_popularity_scores = await asyncio.gather(
            searches_repo.get_user_click_preferences(user_id),
            self._build_para_ti_user_profile(user_id),
            self._build_recent_popularity_scores(days=30),
        )

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)
            category_id = (
                str(product.categoryId) if getattr(product, "categoryId", None) else None
            )

            clicked = search_clicks.get(pid, 0.0)
            category_affinity = (
                user_profile["category_affinity"].get(category_id, 0.0)
                if category_id
                else 0.0
            )
            branch_affinity = user_profile["branch_affinity"].get(
                str(product.branchId), 0.0
            )
            recent_popularity = recent_popularity_scores.get(pid, 0.0)

            final_score = (
                clicked * self.BUSQUEDAS_SEARCH_INTENT
                + category_affinity * self.BUSQUEDAS_CATEGORY_AFFINITY
                + branch_affinity * self.BUSQUEDAS_BRANCH_AFFINITY
                + recent_popularity * self.BUSQUEDAS_RECENT_POPULARITY
            )

            # Keep this section anchored to search-driven affinity, not just global popularity.
            if clicked > 0 or category_affinity > 0 or branch_affinity > 0:
                scored_products.append(
                    ScoredFeedProduct(
                        product=product,
                        score=final_score,
                        section_scores={
                            "clicked_in_searches": clicked,
                            "category_affinity": category_affinity,
                            "branch_affinity": branch_affinity,
                            "recent_popularity": recent_popularity,
                        },
                    )
                )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_nuevos_lugares_favoritos_section(
        self,
        user_id: str,
        branch_ids: Set[str],
        limit: int = 10,
        days: int = 30,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 5: Nuevos en tus Lugares Favoritos
        branch_affinity (50%) + freshness (30%) + popularity (20%)
        """
        # Get user's liked branches, intersected with the tipo filter
        liked_branches = await branch_likes_repo.get_user_preferences(user_id)
        liked_branches = [b for b in liked_branches if str(b) in branch_ids]

        if not liked_branches:
            return []

        liked_branches_set = {str(b) for b in liked_branches}
        branch_products = [
            p for p in (all_products or []) if str(p.branchId) in liked_branches_set
        ]

        if not branch_products:
            return []

        # Get signals in parallel
        branch_popularity, popularity_favorites, popularity_cart = await asyncio.gather(
            branch_likes_repo.get_popularity_scores(),
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        freshness_scores = products_repo.calculate_freshness_scores(branch_products)

        # Calculate scores
        scored_products = []
        for product in branch_products:
            pid = str(product.id)

            # Branch affinity (how popular is this branch)
            branch_affinity = branch_popularity.get(str(product.branchId), 0.5)

            # Freshness
            freshness = freshness_scores.get(pid, 0.0)

            # Popularity
            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Final score
            final_score = (
                branch_affinity * self.NUEVOS_BRANCH_AFFINITY
                + freshness * self.NUEVOS_FRESHNESS
                + popularity * self.NUEVOS_POPULARITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "branch_affinity": branch_affinity,
                        "freshness": freshness,
                        "popularity": popularity,
                    },
                )
            )

        # Sort and limit
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[: self._candidate_limit(limit)]

    async def get_mas_favoriteados_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 6: Los Más Favoriteados
        favorites_count (60%) + cart_count (25%) + proximity (15%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get signals in parallel
        popularity_favorites, popularity_cart = await asyncio.gather(
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            favorites = popularity_favorites.get(pid, 0.0)
            cart = popularity_cart.get(pid, 0.0)
            proximity = proximity_map.get(pid, 0.0)

            # Final score
            final_score = (
                favorites * self.FAVORITEADOS_FAVORITES
                + cart * self.FAVORITEADOS_CART
                + proximity * self.FAVORITEADOS_PROXIMITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "favorites": favorites,
                        "cart": cart,
                        "proximity": proximity,
                    },
                )
            )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_cerca_de_ti_section(
        self,
        user_location: tuple,
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 7: Cerca de Ti
        proximity (70%) + availability (20%) + popularity (10%)
        """
        # Filter to available products from the pre-fetched list
        products = [
            p
            for p in (all_products or [])
            if str(p.branchId) in branch_ids and getattr(p, "availability", False)
        ]
        if not products:
            return []

        popularity_favorites, popularity_cart = await asyncio.gather(
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            proximity = proximity_map.get(pid, 0.0)
            availability = 1.0 if product.availability else 0.0

            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Final score
            final_score = (
                proximity * self.CERCA_PROXIMITY
                + availability * self.CERCA_AVAILABILITY
                + popularity * self.CERCA_POPULARITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "proximity": proximity,
                        "availability": availability,
                        "popularity": popularity,
                    },
                )
            )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_te_podria_gustar_section(
        self,
        user_id: str,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 8: Te Podría Gustar
        category affinity (40%) + branch affinity (20%) + novelty (15%)
        + proximity (15%) + recent popularity (10%)
        """
        products = [
            p
            for p in (all_products or [])
            if str(p.branchId) in branch_ids and getattr(p, "availability", False)
        ]
        if not products:
            return []

        user_profile, recent_popularity_scores = await asyncio.gather(
            self._build_para_ti_user_profile(user_id),
            self._build_recent_popularity_scores(days=30),
        )

        products, proximity_map = await self._prepare_products_with_proximity(
            products,
            user_location,
            radius_km=radius_km,
        )
        if not products:
            return []

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)
            category_id = str(product.categoryId) if getattr(product, "categoryId", None) else None

            # Skip explicit positives and highly consumed products; this section should explore adjacent items.
            if (
                pid in user_profile["favorite_products"]
                or pid in user_profile["cart_products"]
                or user_profile["product_intent"].get(pid, 0.0) >= 0.65
            ):
                continue

            category_affinity = (
                user_profile["category_affinity"].get(category_id, 0.0)
                if category_id
                else 0.0
            )
            branch_affinity = user_profile["branch_affinity"].get(str(product.branchId), 0.0)
            recent_intent = user_profile["product_intent"].get(pid, 0.0)
            novelty = max(0.0, 1.0 - recent_intent)
            proximity = proximity_map.get(pid, 0.0)
            recent_popularity = recent_popularity_scores.get(pid, 0.0)

            # Final score
            final_score = (
                category_affinity * self.GUSTAR_CATEGORY_AFFINITY
                + branch_affinity * self.GUSTAR_BRANCH_AFFINITY
                + novelty * self.GUSTAR_NOVELTY
                + proximity * self.GUSTAR_PROXIMITY
                + recent_popularity * self.GUSTAR_RECENT_POPULARITY
            )

            if final_score > 0:
                scored_products.append(
                    ScoredFeedProduct(
                        product=product,
                        score=final_score,
                        section_scores={
                            "category_affinity": category_affinity,
                            "branch_affinity": branch_affinity,
                            "novelty": novelty,
                            "recent_intent": recent_intent,
                            "proximity": proximity,
                            "recent_popularity": recent_popularity,
                        },
                    )
                )

        # Sort and limit
        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_qdrant_recomendado_section(
        self,
        user_id: str,
        branch_ids: Set[str],
        limit: int = 10,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section: Especialmente para Ti (Qdrant Vector Similarity)
        Uses Qdrant's native recommend API: averages the embeddings of the user's
        favorited and cart products and returns the nearest neighbors.
        Falls back silently to [] if Qdrant is unavailable or the user has no history.
        """
        try:
            import uuid as _uuid
            from clients import get_qdrant_client
            from qdrant_client.models import (
                RecommendInput,
                RecommendQuery,
                RecommendStrategy,
            )

            _UUID_NS = _uuid.UUID("b1e7a000-0000-0000-0000-000000000000")

            user_profile = await self._build_para_ti_user_profile(user_id)

            # Favorites are the strongest purchase-intent signal; cart adds breadth
            positive_mongo_ids: List[str] = list(user_profile["favorite_products"])
            for pid in user_profile["cart_products"]:
                if pid not in positive_mongo_ids:
                    positive_mongo_ids.append(pid)

            if not positive_mongo_ids:
                return []

            # Cap at 10 positives — enough for Qdrant vector averaging
            positive_mongo_ids = positive_mongo_ids[:10]

            positive_uuids = [
                str(_uuid.uuid5(_UUID_NS, mid)) for mid in positive_mongo_ids
            ]

            qdrant_client = get_qdrant_client()

            response = await qdrant_client.query_points(
                collection_name="products",
                query=RecommendQuery(
                    # BEST_SCORE scores each candidate by its max similarity to ANY
                    # positive (favorite/cart) instead of to their averaged centroid.
                    # This respects diverse tastes (e.g. sushi AND cake) instead of
                    # recommending the muddy middle.
                    recommend=RecommendInput(
                        positive=positive_uuids,
                        strategy=RecommendStrategy.BEST_SCORE,
                    )
                ),
                limit=limit * 3,
            )
            results = response.points if hasattr(response, "points") else response

            if not results:
                return []

            # Exclude products the user already explicitly interacted with
            excluded_ids = user_profile["favorite_products"] | user_profile["cart_products"]

            qdrant_score_map: Dict[str, float] = {}
            recommended_order: List[str] = []
            for r in results:
                mongo_id = r.payload.get("mongo_id")
                if mongo_id and mongo_id not in excluded_ids:
                    qdrant_score_map[mongo_id] = float(r.score)
                    recommended_order.append(mongo_id)

            if not recommended_order:
                return []

            # Intersect with all_products pool (respects branch_tipo filter + availability)
            products_by_id = {
                str(p.id): p
                for p in (all_products or [])
                if str(p.branchId) in branch_ids and getattr(p, "availability", False)
            }

            scored_products = []
            for mongo_id in recommended_order:
                product = products_by_id.get(mongo_id)
                if product:
                    score = qdrant_score_map[mongo_id]
                    scored_products.append(
                        ScoredFeedProduct(
                            product=product,
                            score=score,
                            section_scores={"qdrant_similarity": score},
                        )
                    )

            # Diversify so the section is not flooded by a single branch/category
            # (nearest-neighbours cluster heavily). Relevance still dominates.
            from services.recommendation_diversity import diversify

            def _branch_key(sp):
                bid = getattr(sp.product, "branchId", None)
                return str(bid) if bid else None

            def _category_key(sp):
                cid = getattr(sp.product, "categoryId", None)
                return str(cid) if cid else None

            return diversify(
                scored_products,
                score_fn=lambda sp: sp.score,
                key_fns=[_branch_key, _category_key],
                penalty=0.1,
                limit=self._candidate_limit(limit),
            )

        except Exception as e:
            print(f"[Feed] Qdrant recommend error: {type(e).__name__}: {e}")
            return []

    async def get_pide_de_nuevo_section(
        self,
        user_id: str,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section: Pide de Nuevo
        Products the user has previously ordered, ranked by recency (55%) + frequency (35%)
        + proximity (10%). Only shows available products still in the catalog.
        """
        orders, _ = await orders_repo.get_by_customer(
            user_id, status=None, limit=50
        )
        if not orders:
            return []

        product_signals: Dict[str, Dict[str, Any]] = {}
        for order in orders:
            order_time = getattr(order, "completedAt", None) or getattr(order, "createdAt", None)
            for item in order.items:
                if item.itemType != "product":
                    continue
                pid = str(item.itemId)
                if pid not in product_signals:
                    product_signals[pid] = {"latest_at": order_time, "count": 0}
                else:
                    if order_time and (
                        product_signals[pid]["latest_at"] is None
                        or order_time > product_signals[pid]["latest_at"]
                    ):
                        product_signals[pid]["latest_at"] = order_time
                product_signals[pid]["count"] += 1

        if not product_signals:
            return []

        max_count = max(sig["count"] for sig in product_signals.values())
        ordered_ids = set(product_signals.keys())

        products = [
            p
            for p in (all_products or [])
            if (
                str(p.id) in ordered_ids
                and str(p.branchId) in branch_ids
                and getattr(p, "availability", False)
            )
        ]
        if not products:
            return []

        products, proximity_map = await self._prepare_products_with_proximity(
            products, user_location, radius_km=radius_km
        )
        if not products:
            return []

        scored_products = []
        for product in products:
            pid = str(product.id)
            signal = product_signals[pid]
            recency = self._decay_factor(signal["latest_at"], half_life_days=30.0)
            frequency = signal["count"] / max_count
            proximity = proximity_map.get(pid, 0.0)

            final_score = (
                recency * self.PIDE_NUEVO_RECENCY
                + frequency * self.PIDE_NUEVO_FREQUENCY
                + proximity * self.PIDE_NUEVO_PROXIMITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "recency": recency,
                        "frequency": frequency,
                        "proximity": proximity,
                    },
                )
            )

        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    async def get_hora_del_dia_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        radius_km: Optional[float] = None,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section: Hora del Día
        Available products ranked by last-24h activity (60%) + proximity (30%)
        + freshness (10%). Title is time-contextual (see get_meal_context).
        """
        products = [
            p
            for p in (all_products or [])
            if str(p.branchId) in branch_ids and getattr(p, "availability", False)
        ]
        if not products:
            return []

        recent_popularity, (products, proximity_map) = await asyncio.gather(
            self._build_recent_popularity_scores(days=1),
            self._prepare_products_with_proximity(products, user_location, radius_km=radius_km),
        )
        if not products:
            return []

        freshness_scores = products_repo.calculate_freshness_scores(products)

        scored_products = []
        for product in products:
            pid = str(product.id)
            recent_pop = recent_popularity.get(pid, 0.0)
            proximity = proximity_map.get(pid, 0.0)
            freshness = freshness_scores.get(pid, 0.0)

            final_score = (
                recent_pop * self.HORA_DIA_RECENT_POPULARITY
                + proximity * self.HORA_DIA_PROXIMITY
                + freshness * self.HORA_DIA_FRESHNESS
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "recent_popularity_24h": recent_pop,
                        "proximity": proximity,
                        "freshness": freshness,
                    },
                )
            )

        self._sort_scored_products(scored_products)
        return scored_products[: self._candidate_limit(limit)]

    def _deduplicate_sections(
        self,
        sections: List[List[ScoredFeedProduct]],
        target_limit: Optional[int] = None,
    ) -> List[List[ScoredFeedProduct]]:
        """
        Remove duplicate products across sections, keeping first occurrence and
        backfilling each section with the next unique candidates available.

        Args:
            sections: List of section results (each is a list of ScoredFeedProduct)

        Returns:
            Deduplicated sections
        """
        seen_ids: Set[str] = set()
        deduplicated_sections = []

        for section in sections:
            deduplicated_section = []
            for scored_product in section:
                pid = str(scored_product.product.id)
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    deduplicated_section.append(scored_product)
                    if target_limit is not None and len(deduplicated_section) >= target_limit:
                        break
            deduplicated_sections.append(deduplicated_section)

        return deduplicated_sections

    async def get_explorar_section(
        self,
        all_products: List[Any],
        seen_ids: Set[str],
        page: int = 0,
        limit: int = 20,
        user_location: Optional[tuple] = None,
        radius_km: Optional[float] = None,
    ) -> List[ScoredFeedProduct]:
        """Catch-all section: remaining products not shown elsewhere, scored by popularity + freshness + proximity."""
        remaining = [
            p for p in all_products
            if str(p.id) not in seen_ids and getattr(p, "availability", False)
        ]
        # Fallback: if every product was already shown in other sections, show all of them.
        if not remaining:
            remaining = [p for p in all_products if getattr(p, "availability", False)]
        if not remaining:
            return []

        recent_popularity, (remaining, proximity_map) = await asyncio.gather(
            self._build_recent_popularity_scores(days=7),
            self._prepare_products_with_proximity(remaining, user_location, radius_km=radius_km),
        )
        if not remaining:
            return []

        freshness_scores = products_repo.calculate_freshness_scores(remaining)

        scored: List[ScoredFeedProduct] = []
        for product in remaining:
            pid = str(product.id)
            pop = recent_popularity.get(pid, 0.0)
            fresh = freshness_scores.get(pid, 0.0)
            prox = proximity_map.get(pid, 0.0)
            scored.append(
                ScoredFeedProduct(
                    product=product,
                    score=pop * 0.50 + fresh * 0.30 + prox * 0.20,
                    section_scores={"recent_popularity": pop, "freshness": fresh, "proximity": prox},
                )
            )

        self._sort_scored_products(scored)
        offset = page * limit
        # Return limit+1 so the caller can detect whether more pages exist
        return scored[offset: offset + limit + 1]


# Singleton instance
feed_service = FeedService()
