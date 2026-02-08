"""Searches repository for database operations."""
from typing import Optional, Dict, Any, List
from bson import ObjectId
from datetime import datetime
from clients import get_database
from domain.models import Search, ClickedItem


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

    async def get_popular_products_for_query(
        self,
        query: str,
        limit: int = 100
    ) -> Dict[str, float]:
        """
        Get popularity scores for products based on clicks for a query.
        Returns dict mapping product_id to normalized popularity score (0-1).
        """
        db = get_database()

        # Aggregate clicks per product for this query
        pipeline = [
            {"$match": {"query": {"$regex": query, "$options": "i"}}},
            {"$unwind": "$clickedItems"},
            {"$match": {"clickedItems.itemType": "product"}},
            {"$group": {
                "_id": "$clickedItems.itemId",
                "totalClicks": {"$sum": {"$size": "$clickedItems.clicks"}},
                "uniqueUsers": {"$addToSet": "$userId"}
            }},
            {"$project": {
                "productId": "$_id",
                "totalClicks": 1,
                "uniqueUsers": {"$size": "$uniqueUsers"}
            }},
            {"$limit": limit}
        ]

        results = await db[self.collection_name].aggregate(pipeline).to_list(length=limit)

        # Normalize scores 0-1
        if not results:
            return {}

        max_clicks = max(r["totalClicks"] for r in results)
        if max_clicks == 0:
            return {}

        return {
            r["productId"]: r["totalClicks"] / max_clicks
            for r in results
        }

    async def get_user_click_preferences(self, user_id: str) -> Dict[str, float]:
        """
        Get user's click preferences based on search history.
        Returns dict mapping product_id to normalized preference score (0-1).
        """
        searches = await self.get_user_searches(user_id, limit=100)

        product_clicks = {}
        for search in searches:
            for item in search.clickedItems:
                if item.itemType == "product":
                    product_clicks[item.itemId] = product_clicks.get(item.itemId, 0) + len(item.clicks)

        # Normalize scores 0-1
        if not product_clicks:
            return {}

        max_clicks = max(product_clicks.values())
        if max_clicks == 0:
            return {}

        return {k: v / max_clicks for k, v in product_clicks.items()}

    async def get_recent_activity(self, days: int = 7) -> Dict[str, Dict[str, Any]]:
        """
        Get recent activity on products in the last N days.
        Returns dict mapping product_id to activity metrics.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            Dict[product_id: {"clicks": int, "unique_users": int}]
        """
        from datetime import timedelta

        db = get_database()
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Aggregate recent clicks per product
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff_date}}},
            {"$unwind": "$clickedItems"},
            {"$match": {"clickedItems.itemType": "product"}},
            {"$unwind": "$clickedItems.clicks"},
            {"$match": {"clickedItems.clicks": {"$gte": cutoff_date}}},
            {"$group": {
                "_id": "$clickedItems.itemId",
                "totalClicks": {"$sum": 1},
                "uniqueUsers": {"$addToSet": "$userId"}
            }},
            {"$project": {
                "productId": "$_id",
                "totalClicks": 1,
                "uniqueUsers": {"$size": "$uniqueUsers"}
            }}
        ]

        results = await db[self.collection_name].aggregate(pipeline).to_list(length=None)

        return {
            r["productId"]: {
                "clicks": r["totalClicks"],
                "unique_users": r["uniqueUsers"]
            }
            for r in results
        }

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
