"""Re-ranking service for post-processing vector search results."""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from repositories import searches_repo
from repositories.favorites_cart_repository import FavoritesCartRepository
from services.scoring_service import scoring_service


favorites_cart_repo = FavoritesCartRepository()


@dataclass
class RankedProduct:
    """Product with combined scores breakdown."""
    product: Any
    vector_score: float
    popularity_score: float
    proximity_score: float
    personalization_score: float
    final_score: float


class ReRankingService:
    """
    Service for re-ranking vector search results.

    Combines multiple signals:
    - Vector similarity (35%)
    - Popularity from clicks/favorites/cart (30%)
    - Geographic proximity (20%)
    - Personal preferences (15%)
    """

    # Pesos configurables
    WEIGHT_VECTOR = 0.35
    WEIGHT_POPULARITY = 0.30
    WEIGHT_PROXIMITY = 0.20
    WEIGHT_PERSONAL = 0.15

    # Sub-pesos para popularidad
    POPULARITY_CLICKS_WEIGHT = 0.60
    POPULARITY_FAVORITES_WEIGHT = 0.25
    POPULARITY_CART_WEIGHT = 0.15

    # Sub-pesos para personalización
    PERSONAL_CLICKS_WEIGHT = 0.50
    PERSONAL_FAVORITES_WEIGHT = 0.30
    PERSONAL_CART_WEIGHT = 0.20

    async def rerank_products(
        self,
        products: List[Any],
        query: str,
        user_id: Optional[str] = None,
        user_location: Optional[tuple] = None,
        vector_scores: Optional[Dict[str, float]] = None
    ) -> List[RankedProduct]:
        """
        Re-rank products combining vector similarity, popularity, proximity, and personalization.

        Args:
            products: List of Product objects
            query: Search query
            user_id: User ID for personalization
            user_location: (lon, lat) tuple for proximity
            vector_scores: Dict mapping product_id to vector similarity score

        Returns:
            List of RankedProduct sorted by final_score (highest first)
        """
        if not products:
            return []

        # Get popularity signals
        popularity_clicks = await searches_repo.get_popular_products_for_query(query)
        popularity_favorites = await favorites_cart_repo.get_popularity_scores("favorite")
        popularity_cart = await favorites_cart_repo.get_popularity_scores("cart")

        # Get personalization signals
        personal_clicks = {}
        personal_favorites_list = []
        personal_cart_list = []

        if user_id:
            personal_clicks = await searches_repo.get_user_click_preferences(user_id)
            personal_favorites_list = await favorites_cart_repo.get_user_preferences(user_id, "favorite")
            personal_cart_list = await favorites_cart_repo.get_user_preferences(user_id, "cart")

        # Calculate proximity scores
        proximity_map = {}
        if user_location:
            scored_items = await scoring_service.score_products_by_branch(
                products, user_location
            )
            proximity_map = {item.id: item.score for item in scored_items}

        # Build ranked products
        ranked_products = []

        for product in products:
            product_id = product.id

            # 1. Vector score (from Qdrant)
            vector_score = vector_scores.get(product_id, 0.5) if vector_scores else 0.5

            # 2. Popularity score (global signals)
            pop_clicks = popularity_clicks.get(product_id, 0.0)
            pop_favorites = popularity_favorites.get(product_id, 0.0)
            pop_cart = popularity_cart.get(product_id, 0.0)

            popularity_score = (
                pop_clicks * self.POPULARITY_CLICKS_WEIGHT +
                pop_favorites * self.POPULARITY_FAVORITES_WEIGHT +
                pop_cart * self.POPULARITY_CART_WEIGHT
            )

            # 3. Proximity score
            proximity_score = proximity_map.get(product_id, 0.0)

            # 4. Personalization score (user-specific signals)
            pers_clicks = personal_clicks.get(product_id, 0.0)
            pers_favorites = 1.0 if product_id in personal_favorites_list else 0.0
            pers_cart = 1.0 if product_id in personal_cart_list else 0.0

            personalization_score = (
                pers_clicks * self.PERSONAL_CLICKS_WEIGHT +
                pers_favorites * self.PERSONAL_FAVORITES_WEIGHT +
                pers_cart * self.PERSONAL_CART_WEIGHT
            )

            # 5. Calculate final weighted score
            final_score = (
                vector_score * self.WEIGHT_VECTOR +
                popularity_score * self.WEIGHT_POPULARITY +
                proximity_score * self.WEIGHT_PROXIMITY +
                personalization_score * self.WEIGHT_PERSONAL
            )

            ranked_products.append(RankedProduct(
                product=product,
                vector_score=vector_score,
                popularity_score=popularity_score,
                proximity_score=proximity_score,
                personalization_score=personalization_score,
                final_score=final_score
            ))

        # Sort by final score (highest first)
        ranked_products.sort(key=lambda x: x.final_score, reverse=True)

        # Debug logging
        print(f"\n🔍 Re-ranking for query: '{query}'")
        print(f"   Products: {len(ranked_products)}")
        if ranked_products:
            print(f"   Top 3 results:")
            for i, rp in enumerate(ranked_products[:3], 1):
                print(f"     {i}. {rp.product.name[:30]}")
                print(f"        Vec:{rp.vector_score:.2f} | Pop:{rp.popularity_score:.2f} | "
                      f"Prox:{rp.proximity_score:.2f} | Pers:{rp.personalization_score:.2f} "
                      f"→ Final:{rp.final_score:.2f}")

        return ranked_products


# Singleton instance
reranking_service = ReRankingService()
