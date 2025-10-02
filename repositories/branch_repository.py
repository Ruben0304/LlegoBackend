"""Branch repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import Branch


class BranchRepository:
    collection_name = "branches"

    async def get_all(self) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find()
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    async def get_by_id(self, branch_id: str) -> Optional[Branch]:
        db = get_database()
        # Convert string ID to ObjectId for MongoDB query
        try:
            object_id = ObjectId(branch_id)
        except:
            object_id = branch_id
        branch = await db[self.collection_name].find_one({"_id": object_id})
        return Branch(**self._convert_id(branch)) if branch else None

    async def search(self, query: str) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"address": {"$regex": query, "$options": "i"}}
            ]
        })
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    async def get_by_business(self, business_id: str) -> List[Branch]:
        db = get_database()
        cursor = db[self.collection_name].find({"businessId": business_id})
        branches = await cursor.to_list(length=None)
        return [Branch(**self._convert_id(b)) for b in branches]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
