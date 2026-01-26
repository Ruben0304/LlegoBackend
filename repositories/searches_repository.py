"""Searches repository for database operations."""
from typing import Optional, Dict, Any, List
from bson import ObjectId
from datetime import datetime
from clients import get_database
from models import Search, ClickedItem


class SearchesRepository:
    collection_name = "searches"

    async def create_search(self, user_id: str, query: str) -> Optional[Search]:
        """
        Create a new search record.

        Args:
            user_id: The user ID
            query: The search query text

        Returns:
            Search object
        """
        db = get_database()

        new_search = {
            "userId": user_id,
            "query": query,
            "clickedItems": [],
            "createdAt": datetime.utcnow()
        }

        result = await db[self.collection_name].insert_one(new_search)
        new_search["_id"] = result.inserted_id

        return Search(**self._convert_id(new_search))

    async def track_click(
        self,
        user_id: str,
        query: str,
        item_id: str,
        item_type: str
    ) -> Optional[Search]:
        """
        Track a click on an item from a search.
        Creates search if it doesn't exist, adds item to clickedItems or updates click count.

        Args:
            user_id: The user ID
            query: The search query
            item_id: The clicked item ID
            item_type: "product" or "business"

        Returns:
            Updated Search object
        """
        db = get_database()

        # Find the most recent search with this query for this user
        search = await db[self.collection_name].find_one(
            {"userId": user_id, "query": query},
            sort=[("createdAt", -1)]
        )

        # If no search exists, create one
        if not search:
            return await self._create_search_with_click(user_id, query, item_id, item_type)

        # Check if this item already exists in clickedItems
        item_exists = False
        for item in search.get("clickedItems", []):
            if item["itemId"] == item_id and item["itemType"] == item_type:
                item_exists = True
                break

        if item_exists:
            # Update: add new timestamp to clicks array
            result = await db[self.collection_name].find_one_and_update(
                {
                    "_id": search["_id"],
                    "clickedItems.itemId": item_id,
                    "clickedItems.itemType": item_type
                },
                {
                    "$push": {
                        "clickedItems.$.clicks": datetime.utcnow()
                    }
                },
                return_document=True
            )
        else:
            # Add new item to clickedItems array
            new_clicked_item = {
                "itemId": item_id,
                "itemType": item_type,
                "clicks": [datetime.utcnow()]
            }
            result = await db[self.collection_name].find_one_and_update(
                {"_id": search["_id"]},
                {
                    "$push": {
                        "clickedItems": new_clicked_item
                    }
                },
                return_document=True
            )

        return Search(**self._convert_id(result)) if result else None

    async def _create_search_with_click(
        self,
        user_id: str,
        query: str,
        item_id: str,
        item_type: str
    ) -> Optional[Search]:
        """
        Create a new search with initial clicked item.

        Args:
            user_id: The user ID
            query: The search query
            item_id: The clicked item ID
            item_type: "product" or "business"

        Returns:
            New Search object
        """
        db = get_database()

        new_search = {
            "userId": user_id,
            "query": query,
            "clickedItems": [{
                "itemId": item_id,
                "itemType": item_type,
                "clicks": [datetime.utcnow()]
            }],
            "createdAt": datetime.utcnow()
        }

        result = await db[self.collection_name].insert_one(new_search)
        new_search["_id"] = result.inserted_id

        return Search(**self._convert_id(new_search))

    async def get_user_searches(self, user_id: str, limit: int = 50) -> List[Search]:
        """
        Get recent searches for a user.

        Args:
            user_id: The user ID
            limit: Maximum number of searches to return

        Returns:
            List of Search objects
        """
        db = get_database()
        cursor = db[self.collection_name].find(
            {"userId": user_id}
        ).sort("createdAt", -1).limit(limit)

        searches = await cursor.to_list(length=limit)
        return [Search(**self._convert_id(search)) for search in searches]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
