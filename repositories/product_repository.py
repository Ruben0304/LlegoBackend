"""Product repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import Product


class ProductRepository:
    collection_name = "products"

    async def get_all(self) -> List[Product]:
        db = get_database()
        cursor = db[self.collection_name].find()
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    async def get_by_id(self, product_id: str) -> Optional[Product]:
        db = get_database()
        # Convert string ID to ObjectId for MongoDB query
        try:
            object_id = ObjectId(product_id)
        except:
            object_id = product_id
        product = await db[self.collection_name].find_one({"_id": object_id})
        return Product(**self._convert_id(product)) if product else None

    async def search(self, query: str) -> List[Product]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]
        })
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    async def get_by_branch(self, branch_id: str) -> List[Product]:
        db = get_database()
        cursor = db[self.collection_name].find({"branchId": branch_id})
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    async def get_available(self) -> List[Product]:
        db = get_database()
        cursor = db[self.collection_name].find({"availability": True})
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    async def get_by_ids(self, product_ids: List[str]) -> List[Product]:
        db = get_database()
        # Convert string IDs to ObjectIds for MongoDB query
        object_ids = []
        for product_id in product_ids:
            try:
                object_ids.append(ObjectId(product_id))
            except:
                object_ids.append(product_id)

        cursor = db[self.collection_name].find({"_id": {"$in": object_ids}})
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
