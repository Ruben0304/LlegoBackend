"""User repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import User


class UserRepository:
    collection_name = "users"

    async def get_all(self) -> List[User]:
        db = get_database()
        cursor = db[self.collection_name].find()
        users = await cursor.to_list(length=None)
        return [User(**self._convert_id(user)) for user in users]

    async def get_by_id(self, user_id: str) -> Optional[User]:
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id
        user = await db[self.collection_name].find_one({"_id": object_id})
        return User(**self._convert_id(user)) if user else None

    async def search(self, query: str) -> List[User]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}}
            ]
        })
        users = await cursor.to_list(length=None)
        return [User(**self._convert_id(user)) for user in users]

    async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update a user in MongoDB."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def add_business_id(self, user_id: str, business_id: str) -> Optional[User]:
        """Add a business ID to the user's businessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$addToSet": {"businessIds": business_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_business_id(self, user_id: str, business_id: str) -> Optional[User]:
        """Remove a business ID from the user's businessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"businessIds": business_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def add_branch_id(self, user_id: str, branch_id: str) -> Optional[User]:
        """Add a branch ID to the user's branchIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$addToSet": {"branchIds": branch_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_branch_id(self, user_id: str, branch_id: str) -> Optional[User]:
        """Remove a branch ID from the user's branchIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"branchIds": branch_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def delete(self, user_id: str) -> bool:
        """Delete a user from MongoDB."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
