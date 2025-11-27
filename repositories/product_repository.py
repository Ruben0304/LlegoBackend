"""Product repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database, get_qdrant_client
from models import Product
from qdrant_client.http import models as qdrant_models


class ProductRepository:
    collection_name = "products"
    qdrant_collection_name = "products"

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
        """Get products by IDs from Qdrant."""
        try:
            qdrant_client = get_qdrant_client()

            # Retrieve points from Qdrant using scroll with filter
            # We need to filter by metadata.mongo_id
            products = []

            for product_id in product_ids:
                # Search for point with this mongo_id in metadata
                result = await qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    scroll_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.mongo_id",
                                match=qdrant_models.MatchValue(value=product_id)
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False
                )

                points, _ = result

                if points:
                    point = points[0]
                    metadata = point.payload.get("metadata", {})

                    # Reconstruct Product from metadata
                    product_data = {
                        "_id": metadata.get("mongo_id"),
                        "name": metadata.get("name"),
                        "description": metadata.get("description"),
                        "price": metadata.get("price"),
                        "currency": metadata.get("currency", "USD"),
                        "weight": metadata.get("weight"),
                        "availability": metadata.get("availability", False),
                        "image": metadata.get("image"),
                        "branchId": metadata.get("branchId"),
                        "categoryId": metadata.get("categoryId"),
                        "createdAt": metadata.get("createdAt")
                    }

                    products.append(Product(**product_data))

            return products

        except Exception as e:
            print(f"Error fetching products from Qdrant: {e}")
            # Fallback to empty list if Qdrant fails
            return []

    async def get_by_category(self, category_id: str) -> List[Product]:
        db = get_database()
        cursor = db[self.collection_name].find({"categoryId": category_id})
        products = await cursor.to_list(length=None)
        return [Product(**self._convert_id(p)) for p in products]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
