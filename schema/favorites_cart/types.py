"""GraphQL types for FavoritesCart entity."""
import strawberry
from datetime import datetime


@strawberry.type
class FavoriteCartType:
    id: str
    userId: str
    productId: str
    type: str  # "favorite" or "cart"
    createdAt: datetime
