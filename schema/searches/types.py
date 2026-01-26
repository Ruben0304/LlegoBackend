"""GraphQL types for Search entity."""
import strawberry
from datetime import datetime
from typing import List


@strawberry.type
class ClickedItemType:
    itemId: str
    itemType: str  # "product" or "business"
    clicks: List[datetime]


@strawberry.type
class SearchType:
    id: str
    userId: str
    query: str
    clickedItems: List[ClickedItemType]
    createdAt: datetime
