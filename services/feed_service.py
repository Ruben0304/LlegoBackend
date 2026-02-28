"""Feed service for personalized product recommendations."""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from repositories import (
    branch_likes_repo,
    branches_repo,
    favorites_cart_repo,
    products_repo,
    searches_repo,
)
from services.scoring_service import scoring_service


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
    PARA_TI_PERSONALIZATION = 0.45
    PARA_TI_POPULARITY = 0.30
    PARA_TI_PROXIMITY = 0.25

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
    BUSQUEDAS_CLICKED = 0.50
    BUSQUEDAS_SIMILAR = 0.30
    BUSQUEDAS_POPULARITY = 0.20

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
    GUSTAR_SIMILARITY = 0.50
    GUSTAR_POPULARITY = 0.30
    GUSTAR_PROXIMITY = 0.20

    async def get_branch_ids_by_tipo(self, branch_tipo: str) -> Set[str]:
        """Fetch branch IDs filtered by tipo. Used once per feed request."""
        print(f"[DEBUG] get_branch_ids_by_tipo - Fetching branch IDs for tipo: {branch_tipo}")
        ids = await branches_repo.get_ids_by_tipo(branch_tipo.lower())
        print(f"[DEBUG] get_branch_ids_by_tipo - Found {len(ids)} branches for tipo {branch_tipo}")
        if len(ids) > 0:
            print(f"[DEBUG] get_branch_ids_by_tipo - Sample branch IDs (first 5): {list(ids)[:5]}")
        return set(ids)

    async def get_para_ti_section(
        self,
        user_id: str,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 1: Para Ti (Personalizado)
        personalization (45%) + popularity (30%) + proximity (25%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get signals in parallel
        (
            personal_clicks,
            personal_favorites,
            personal_cart,
            popularity_favorites,
            popularity_cart,
        ) = await asyncio.gather(
            searches_repo.get_user_click_preferences(user_id),
            favorites_cart_repo.get_user_preferences(user_id, "favorite"),
            favorites_cart_repo.get_user_preferences(user_id, "cart"),
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            # Personalization
            pers_clicks = personal_clicks.get(pid, 0.0)
            pers_favorites = 1.0 if pid in personal_favorites else 0.0
            pers_cart = 1.0 if pid in personal_cart else 0.0
            personalization = pers_clicks * 0.5 + pers_favorites * 0.3 + pers_cart * 0.2

            # Popularity
            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Proximity
            proximity = proximity_map.get(pid, 0.0)

            # Final score
            final_score = (
                personalization * self.PARA_TI_PERSONALIZATION
                + popularity * self.PARA_TI_POPULARITY
                + proximity * self.PARA_TI_PROXIMITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "personalization": personalization,
                        "popularity": popularity,
                        "proximity": proximity,
                    },
                )
            )

        # Sort and limit
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    async def get_populares_cerca_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
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

        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

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
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    async def get_trending_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        days: int = 7,
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

        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

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
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    async def get_basado_busquedas_section(
        self,
        user_id: str,
        branch_ids: Set[str],
        limit: int = 10,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 4: Basado en tus Búsquedas
        clicked_in_searches (50%) + popularity (50%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get signals in parallel
        personal_clicks, popularity_favorites, popularity_cart = await asyncio.gather(
            searches_repo.get_user_click_preferences(user_id),
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            # Clicked in searches
            clicked = personal_clicks.get(pid, 0.0)

            # Popularity
            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Final score (adjusted weights since we don't have similarity)
            final_score = clicked * 0.70 + popularity * 0.30

            # Only include products with some search activity
            if clicked > 0 or popularity > 0:
                scored_products.append(
                    ScoredFeedProduct(
                        product=product,
                        score=final_score,
                        section_scores={
                            "clicked_in_searches": clicked,
                            "popularity": popularity,
                        },
                    )
                )

        # Sort and limit
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

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
        return scored_products[:limit]

    async def get_mas_favoriteados_section(
        self,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
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

        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

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
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    async def get_cerca_de_ti_section(
        self,
        user_location: tuple,
        branch_ids: Set[str],
        limit: int = 10,
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

        # Get signals in parallel
        proximity_task = None
        if user_location:
            proximity_task = scoring_service.score_products_by_branch(
                products, user_location
            )

        popularity_favorites, popularity_cart = await asyncio.gather(
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        proximity_map = {}
        if proximity_task:
            scored_items = await proximity_task
            proximity_map = {item.id: item.score for item in scored_items}

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
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    async def get_te_podria_gustar_section(
        self,
        user_id: str,
        user_location: Optional[tuple],
        branch_ids: Set[str],
        limit: int = 10,
        all_products: Optional[List[Any]] = None,
    ) -> List[ScoredFeedProduct]:
        """
        Section 8: Te Podría Gustar
        similarity (50%) + popularity (30%) + proximity (20%)
        """
        products = [p for p in (all_products or []) if str(p.branchId) in branch_ids]
        if not products:
            return []

        # Get signals in parallel
        (
            personal_favorites,
            personal_clicks,
            popularity_favorites,
            popularity_cart,
        ) = await asyncio.gather(
            favorites_cart_repo.get_user_preferences(user_id, "favorite"),
            searches_repo.get_user_click_preferences(user_id),
            favorites_cart_repo.get_popularity_scores("favorite"),
            favorites_cart_repo.get_popularity_scores("cart"),
        )

        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

        # Calculate scores
        scored_products = []
        for product in products:
            pid = str(product.id)

            # Skip products user already favorited or clicked frequently
            if pid in personal_favorites or personal_clicks.get(pid, 0) > 0.5:
                continue

            # Similarity (simplified: inverse of how much user interacted)
            interaction = personal_clicks.get(pid, 0.0)
            similarity = 1.0 - interaction

            # Popularity
            pop_fav = popularity_favorites.get(pid, 0.0)
            pop_cart = popularity_cart.get(pid, 0.0)
            popularity = pop_fav * 0.6 + pop_cart * 0.4

            # Proximity
            proximity = proximity_map.get(pid, 0.0)

            # Final score
            final_score = (
                similarity * self.GUSTAR_SIMILARITY
                + popularity * self.GUSTAR_POPULARITY
                + proximity * self.GUSTAR_PROXIMITY
            )

            scored_products.append(
                ScoredFeedProduct(
                    product=product,
                    score=final_score,
                    section_scores={
                        "similarity": similarity,
                        "popularity": popularity,
                        "proximity": proximity,
                    },
                )
            )

        # Sort and limit
        scored_products.sort(key=lambda x: x.score, reverse=True)
        return scored_products[:limit]

    def _deduplicate_sections(
        self, sections: List[List[ScoredFeedProduct]]
    ) -> List[List[ScoredFeedProduct]]:
        """
        Remove duplicate products across sections, keeping first occurrence.

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
            deduplicated_sections.append(deduplicated_section)

        return deduplicated_sections


# Singleton instance
feed_service = FeedService()
