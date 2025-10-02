"""Business repository for database operations."""
from typing import List, Optional, Dict, Any
from clients import get_database
from models import Business


class BusinessRepository:
    collection_name = "bussisnes"

    async def get_all(self) -> List[Business]:
        db = get_database()
        cursor = db[self.collection_name].find()
        businesses = await cursor.to_list(length=None)
        return [Business(**self._convert_id(b)) for b in businesses]

    async def get_by_id(self, business_id: str) -> Optional[Business]:
        db = get_database()
        business = await db[self.collection_name].find_one({"_id": business_id})
        return Business(**self._convert_id(business)) if business else None

    async def search(self, query: str) -> List[Business]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"type": {"$regex": query, "$options": "i"}}
            ]
        })
        businesses = await cursor.to_list(length=None)
        return [Business(**self._convert_id(b)) for b in businesses]

    async def get_by_owner(self, owner_id: str) -> List[Business]:
        db = get_database()
        cursor = db[self.collection_name].find({"ownerId": owner_id})
        businesses = await cursor.to_list(length=None)
        return [Business(**self._convert_id(b)) for b in businesses]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
