"""Product category repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from domain.models import ProductCategory


class ProductCategoryRepository:
    collection_name = "product_categories"

    async def get_all(self) -> List[ProductCategory]:
        """Get all product categories."""
        db = get_database()
        cursor = db[self.collection_name].find()
        categories = await cursor.to_list(length=None)
        return [ProductCategory(**self._convert_id(c)) for c in categories]

    async def get_by_id(self, category_id: str) -> Optional[ProductCategory]:
        """Get product category by ID."""
        db = get_database()
        try:
            object_id = ObjectId(category_id)
        except:
            object_id = category_id
        category = await db[self.collection_name].find_one({"_id": object_id})
        return ProductCategory(**self._convert_id(category)) if category else None

    async def get_by_ids(self, category_ids: List[str]) -> List[ProductCategory]:
        """Batch fetch product categories by IDs in a single query."""
        if not category_ids:
            return []
        db = get_database()
        object_ids = []
        for cid in category_ids:
            try:
                object_ids.append(ObjectId(cid))
            except Exception:
                object_ids.append(cid)
        cursor = db[self.collection_name].find({"_id": {"$in": object_ids}})
        categories = await cursor.to_list(length=None)
        return [ProductCategory(**self._convert_id(c)) for c in categories]

    async def get_by_branch_type(self, branch_type: str) -> List[ProductCategory]:
        """Get product categories for a specific branch type."""
        db = get_database()
        # Normalize branch_type to lowercase to match database storage
        normalized_type = branch_type.lower() if branch_type else None
        cursor = db[self.collection_name].find({"branchType": normalized_type})
        categories = await cursor.to_list(length=None)
        return [ProductCategory(**self._convert_id(c)) for c in categories]

    async def get_by_branch_types(self, branch_types: List[str]) -> List[ProductCategory]:
        """Get product categories for multiple branch types in a single query."""
        if not branch_types:
            return []
        db = get_database()
        normalized = [t.lower() for t in branch_types]
        cursor = db[self.collection_name].find({"branchType": {"$in": normalized}})
        categories = await cursor.to_list(length=None)
        return [ProductCategory(**self._convert_id(c)) for c in categories]

    async def get_by_name(self, name: str, branch_type: Optional[str] = None) -> Optional[ProductCategory]:
        """Get product category by name and optionally branch type."""
        db = get_database()
        query = {"name": name}
        if branch_type:
            # Normalize branch_type to lowercase to match database storage
            query["branchType"] = branch_type.lower()
        category = await db[self.collection_name].find_one(query)
        return ProductCategory(**self._convert_id(category)) if category else None

    async def create(self, category_data: Dict[str, Any]) -> ProductCategory:
        """Create a new product category."""
        db = get_database()
        result = await db[self.collection_name].insert_one(category_data)
        category_data["_id"] = str(result.inserted_id)
        return ProductCategory(**category_data)

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
