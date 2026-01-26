"""GraphQL mutations for Search entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import SearchType, ClickedItemType
from repositories import searches_repo
from utils.graphql_auth import require_auth


@strawberry.type
class SearchesMutation:
    @strawberry.mutation(description="Registrar clic en resultado de búsqueda")
    async def track_search_click(
        self,
        info: Info,
        search_query: str,
        item_id: str,
        item_type: str,
        jwt: Optional[str] = None
    ) -> SearchType:
        """
        Track a click on a search result item.
        Creates or updates search record with clicked item.

        Args:
            search_query: The search query text
            item_id: The clicked item ID (product or business)
            item_type: "product" or "business"
        """
        user_id = require_auth(jwt, info)

        # Validate item_type
        if item_type not in ["product", "business"]:
            raise Exception("item_type debe ser 'product' o 'business'")

        result = await searches_repo.track_click(user_id, search_query, item_id, item_type)

        if not result:
            raise Exception("Error al registrar el clic")

        return SearchType(
            id=result.id,
            userId=result.userId,
            query=result.query,
            clickedItems=[
                ClickedItemType(
                    itemId=item.itemId,
                    itemType=item.itemType,
                    clicks=item.clicks
                )
                for item in result.clickedItems
            ],
            createdAt=result.createdAt
        )
