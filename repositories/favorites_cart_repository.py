"""FavoritesCart repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from clients import get_database
from models import FavoriteCart


class FavoritesCartRepository:
    collection_name = "favorites_cart"

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
            "userId": user_id,
            "productId": product_id,
            "type": item_type
        })

        if existing:
            return None  # Already exists

        # Create new entry
        new_item = {
            "userId": user_id,
            "productId": product_id,
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
            "userId": user_id,
            "productId": product_id,
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
        query = {"userId": user_id}
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
            "userId": user_id,
            "productId": product_id,
            "type": item_type
        })
        return item is not None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
