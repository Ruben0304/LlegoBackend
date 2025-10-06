"""Category repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import Category


class CategoryRepository:
    collection_name = "categories"

    async def get_all(self) -> List[Category]:
        db = get_database()
        cursor = db[self.collection_name].find()
        categories = await cursor.to_list(length=None)
        return [Category(**self._convert_id(c)) for c in categories]

    async def get_by_id(self, category_id: str) -> Optional[Category]:
        db = get_database()
        # Convert string ID to ObjectId for MongoDB query
        try:
            object_id = ObjectId(category_id)
        except:
            object_id = category_id
        category = await db[self.collection_name].find_one({"_id": object_id})
        return Category(**self._convert_id(category)) if category else None

    async def get_by_name(self, name: str) -> Optional[Category]:
        db = get_database()
        category = await db[self.collection_name].find_one({"name": name})
        return Category(**self._convert_id(category)) if category else None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
