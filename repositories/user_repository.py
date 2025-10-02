"""User repository for database operations."""
from typing import List, Optional, Dict, Any
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
        user = await db[self.collection_name].find_one({"_id": user_id})
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

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
