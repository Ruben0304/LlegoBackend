"""Variant list repository for database operations."""

import uuid
from datetime import datetime
from typing import Any, List, Optional

from bson import ObjectId

from clients import get_database
from domain.models import VariantList


class VariantListRepository:
    """Repository for VariantList CRUD operations."""

    mongo_collection_name = "variant_lists"

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    @classmethod
    def _normalize_variant_list_doc(cls, variant_list_data: dict) -> dict:
        """Normalize variant list document for MongoDB."""
        variant_list_data = dict(variant_list_data)
        variant_list_data["_id"] = cls._to_object_id(
            variant_list_data.get("_id", ObjectId())
        )
        variant_list_data["branchId"] = cls._to_object_id(
            variant_list_data.get("branchId")
        )

        # Ensure each option has an ID
        for option in variant_list_data.get("options", []):
            if "id" not in option or not option["id"]:
                option["id"] = str(uuid.uuid4())

        return variant_list_data

    async def create(self, variant_list_data: dict) -> VariantList:
        """Create a new variant list."""
        db = get_database()

        variant_list_data = self._normalize_variant_list_doc(variant_list_data)
        variant_list_data["createdAt"] = datetime.utcnow()
        variant_list_data["updatedAt"] = datetime.utcnow()

        await db[self.mongo_collection_name].insert_one(variant_list_data)
        return VariantList(**variant_list_data)

    async def get_by_id(self, variant_list_id: str) -> Optional[VariantList]:
        """Get variant list by ID."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one(
            {"_id": self._to_object_id(variant_list_id)}
        )
        return VariantList(**doc) if doc else None

    async def get_by_branch(self, branch_id: str) -> List[VariantList]:
        """Get all variant lists for a branch."""
        db = get_database()
        cursor = (
            db[self.mongo_collection_name]
            .find({"branchId": self._to_object_id(branch_id)})
            .sort("createdAt", -1)
        )
        docs = await cursor.to_list(length=None)
        return [VariantList(**doc) for doc in docs]

    async def get_by_ids(self, variant_list_ids: List[str]) -> List[VariantList]:
        """Get variant lists by IDs."""
        if not variant_list_ids:
            return []

        db = get_database()
        object_ids = [self._to_object_id(vid) for vid in variant_list_ids]
        cursor = db[self.mongo_collection_name].find({"_id": {"$in": object_ids}})
        docs = await cursor.to_list(length=None)
        return [VariantList(**doc) for doc in docs]

    async def update(
        self, variant_list_id: str, update_data: dict
    ) -> Optional[VariantList]:
        """Update a variant list."""
        db = get_database()

        normalized_update_data = dict(update_data)
        if "branchId" in normalized_update_data:
            normalized_update_data["branchId"] = self._to_object_id(
                normalized_update_data["branchId"]
            )

        # Ensure each option has an ID
        if "options" in normalized_update_data:
            for option in normalized_update_data["options"]:
                if "id" not in option or not option["id"]:
                    option["id"] = str(uuid.uuid4())

        normalized_update_data["updatedAt"] = datetime.utcnow()

        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(variant_list_id)},
            {"$set": normalized_update_data},
        )
        if result.modified_count > 0:
            return await self.get_by_id(variant_list_id)
        return None

    async def delete(self, variant_list_id: str) -> bool:
        """Delete a variant list."""
        db = get_database()
        result = await db[self.mongo_collection_name].delete_one(
            {"_id": self._to_object_id(variant_list_id)}
        )
        return result.deleted_count > 0


# Singleton instance
variant_lists_repo = VariantListRepository()
