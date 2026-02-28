"""FavoritesCart repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from clients import get_database
from domain.models import FavoriteCart


class FavoritesCartRepository:
    collection_name = "favorites_cart"

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def add(self, user_id: str, product_id: str, item_type: str) -> Optional[FavoriteCart]:
        """
        Add a favorite or cart item. Checks for duplicates before adding.

        Args:
            user_id: The user ID
            product_id: The product ID
            item_type: "favorite" or "cart"

        Returns:
            FavoriteCart object or None if already exists
        """
        db = get_database()

        # Check if already exists
        existing = await db[self.collection_name].find_one({
            "userId": self._to_object_id(user_id),
            "productId": self._to_object_id(product_id),
            "type": item_type
        })

        if existing:
            return None  # Already exists

        # Create new entry
        new_item = {
            "userId": self._to_object_id(user_id),
            "productId": self._to_object_id(product_id),
            "type": item_type,
            "createdAt": datetime.utcnow()
        }

        result = await db[self.collection_name].insert_one(new_item)
        new_item["_id"] = result.inserted_id

        return FavoriteCart(**self._convert_id(new_item))

    async def remove(self, user_id: str, product_id: str, item_type: str) -> bool:
        """
        Remove a favorite or cart item.

        Args:
            user_id: The user ID
            product_id: The product ID
            item_type: "favorite" or "cart"

        Returns:
            True if removed, False otherwise
        """
        db = get_database()
        result = await db[self.collection_name].delete_one({
            "userId": self._to_object_id(user_id),
            "productId": self._to_object_id(product_id),
            "type": item_type
        })
        return result.deleted_count > 0

    async def get_by_user(self, user_id: str, item_type: Optional[str] = None) -> List[FavoriteCart]:
        """
        Get all favorites/cart items for a user.

        Args:
            user_id: The user ID
            item_type: Optional filter by "favorite" or "cart"

        Returns:
            List of FavoriteCart objects
        """
        db = get_database()
        query = {"userId": self._to_object_id(user_id)}
        if item_type:
            query["type"] = item_type

        cursor = db[self.collection_name].find(query)
        items = await cursor.to_list(length=None)
        return [FavoriteCart(**self._convert_id(item)) for item in items]

    async def exists(self, user_id: str, product_id: str, item_type: str) -> bool:
        """
        Check if a favorite/cart item exists.

        Args:
            user_id: The user ID
            product_id: The product ID
            item_type: "favorite" or "cart"

        Returns:
            True if exists, False otherwise
        """
        db = get_database()
        item = await db[self.collection_name].find_one({
            "userId": self._to_object_id(user_id),
            "productId": self._to_object_id(product_id),
            "type": item_type
        })
        return item is not None

    async def get_popularity_scores(self, item_type: str = "favorite") -> Dict[str, float]:
        """
        Get popularity scores for products based on favorites/cart adds.
        Returns dict mapping product_id to normalized popularity score (0-1).

        Args:
            item_type: "favorite" or "cart"
        """
        db = get_database()

        # Aggregate counts per product
        pipeline = [
            {"$match": {"type": item_type}},
            {"$group": {
                "_id": "$productId",
                "count": {"$sum": 1}
            }}
        ]

        results = await db[self.collection_name].aggregate(pipeline).to_list(length=None)

        # Normalize scores 0-1
        if not results:
            return {}

        max_count = max(r["count"] for r in results)
        if max_count == 0:
            return {}

        return {str(r["_id"]): r["count"] / max_count for r in results}

    async def get_user_preferences(self, user_id: str, item_type: str = "favorite") -> List[str]:
        """
        Get list of product IDs that user has favorited/added to cart.

        Args:
            user_id: The user ID
            item_type: "favorite" or "cart"

        Returns:
            List of product IDs
        """
        items = await self.get_by_user(user_id, item_type)
        return [str(item.productId) for item in items]

    async def get_recent_activity(self, item_type: str = "favorite", days: int = 7) -> Dict[str, int]:
        """
        Get favorites/cart items added in the last N days.
        Returns dict mapping product_id to count of additions.

        Args:
            item_type: "favorite" or "cart"
            days: Number of days to look back (default 7)

        Returns:
            Dict[product_id: count]
        """
        from datetime import timedelta

        db = get_database()
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Aggregate counts per product for recent additions
        pipeline = [
            {"$match": {
                "type": item_type,
                "createdAt": {"$gte": cutoff_date}
            }},
            {"$group": {
                "_id": "$productId",
                "count": {"$sum": 1}
            }}
        ]

        results = await db[self.collection_name].aggregate(pipeline).to_list(length=None)

        return {str(r["_id"]): r["count"] for r in results}

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
