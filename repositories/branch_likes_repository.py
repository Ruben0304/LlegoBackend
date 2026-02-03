"""BranchLikes repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from clients import get_database
from models import BranchLike


class BranchLikesRepository:
    collection_name = "branch_likes"

    async def add(self, user_id: str, branch_id: str) -> Optional[BranchLike]:
        """
        Add a branch like. Checks for duplicates before adding.

        Args:
            user_id: The user ID
            branch_id: The branch ID

        Returns:
            BranchLike object or None if already exists
        """
        db = get_database()

        # Check if already exists
        existing = await db[self.collection_name].find_one({
            "userId": user_id,
            "branchId": branch_id
        })

        if existing:
            return None  # Already exists

        # Create new entry
        new_item = {
            "userId": user_id,
            "branchId": branch_id,
            "createdAt": datetime.utcnow()
        }

        result = await db[self.collection_name].insert_one(new_item)
        new_item["_id"] = result.inserted_id

        return BranchLike(**self._convert_id(new_item))

    async def remove(self, user_id: str, branch_id: str) -> bool:
        """
        Remove a branch like.

        Args:
            user_id: The user ID
            branch_id: The branch ID

        Returns:
            True if removed, False otherwise
        """
        db = get_database()
        result = await db[self.collection_name].delete_one({
            "userId": user_id,
            "branchId": branch_id
        })
        return result.deleted_count > 0

    async def get_by_user(self, user_id: str) -> List[BranchLike]:
        """
        Get all branch likes for a user.

        Args:
            user_id: The user ID

        Returns:
            List of BranchLike objects
        """
        db = get_database()
        cursor = db[self.collection_name].find({"userId": user_id})
        items = await cursor.to_list(length=None)
        return [BranchLike(**self._convert_id(item)) for item in items]

    async def exists(self, user_id: str, branch_id: str) -> bool:
        """
        Check if a branch like exists.

        Args:
            user_id: The user ID
            branch_id: The branch ID

        Returns:
            True if exists, False otherwise
        """
        db = get_database()
        item = await db[self.collection_name].find_one({
            "userId": user_id,
            "branchId": branch_id
        })
        return item is not None

    async def get_popularity_scores(self) -> Dict[str, float]:
        """
        Get popularity scores for branches based on likes.
        Returns dict mapping branch_id to normalized popularity score (0-1).
        """
        db = get_database()

        # Aggregate counts per branch
        pipeline = [
            {"$group": {
                "_id": "$branchId",
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

        return {r["_id"]: r["count"] / max_count for r in results}

    async def get_user_preferences(self, user_id: str) -> List[str]:
        """
        Get list of branch IDs that user has liked.

        Args:
            user_id: The user ID

        Returns:
            List of branch IDs
        """
        items = await self.get_by_user(user_id)
        return [item.branchId for item in items]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
