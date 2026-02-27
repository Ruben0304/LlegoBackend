"""Combo repository for database operations."""

import uuid
from datetime import datetime
from typing import Any, List, Optional

from bson import ObjectId

from clients import get_database
from domain.models import Combo


class ComboRepository:
    """Repository for Combo CRUD operations."""

    mongo_collection_name = "combos"

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    @classmethod
    def _normalize_combo_doc(cls, combo_data: dict) -> dict:
        combo_data = dict(combo_data)
        combo_data["_id"] = cls._to_object_id(combo_data.get("_id", ObjectId()))
        combo_data["branchId"] = cls._to_object_id(combo_data.get("branchId"))
        if combo_data.get("categoryId") is not None:
            combo_data["categoryId"] = cls._to_object_id(combo_data["categoryId"])

        for slot in combo_data.get("slots", []):
            if "id" not in slot:
                slot["id"] = str(uuid.uuid4())
            for option in slot.get("options", []):
                option["productId"] = cls._to_object_id(option.get("productId"))

        return combo_data

    async def create(self, combo_data: dict) -> Combo:
        """Create a new combo."""
        db = get_database()

        combo_data = self._normalize_combo_doc(combo_data)
        combo_data["createdAt"] = datetime.utcnow()
        combo_data["updatedAt"] = datetime.utcnow()

        await db[self.mongo_collection_name].insert_one(combo_data)
        return Combo(**combo_data)

    async def get_by_id(self, combo_id: str) -> Optional[Combo]:
        """Get combo by ID."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one(
            {"_id": self._to_object_id(combo_id)}
        )
        return Combo(**doc) if doc else None

    async def get_by_branch(
        self, branch_id: str, available_only: bool = True
    ) -> List[Combo]:
        """Get all combos for a branch."""
        db = get_database()
        query = {"branchId": self._to_object_id(branch_id)}
        if available_only:
            query["availability"] = True

        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [Combo(**doc) for doc in docs]

    async def get_all(self, available_only: bool = False) -> List[Combo]:
        """Get all combos."""
        db = get_database()
        query = {"availability": True} if available_only else {}
        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [Combo(**doc) for doc in docs]

    async def update(self, combo_id: str, update_data: dict) -> Optional[Combo]:
        """Update a combo."""
        db = get_database()

        normalized_update_data = dict(update_data)
        if "branchId" in normalized_update_data:
            normalized_update_data["branchId"] = self._to_object_id(
                normalized_update_data["branchId"]
            )
        if "categoryId" in normalized_update_data and normalized_update_data["categoryId"] is not None:
            normalized_update_data["categoryId"] = self._to_object_id(
                normalized_update_data["categoryId"]
            )
        if "slots" in normalized_update_data:
            for slot in normalized_update_data["slots"]:
                if "id" not in slot:
                    slot["id"] = str(uuid.uuid4())
                for option in slot.get("options", []):
                    option["productId"] = self._to_object_id(option.get("productId"))

        normalized_update_data["updatedAt"] = datetime.utcnow()

        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(combo_id)}, {"$set": normalized_update_data}
        )
        if result.modified_count > 0:
            return await self.get_by_id(combo_id)
        return None

    async def delete(self, combo_id: str) -> bool:
        """Delete a combo."""
        db = get_database()
        result = await db[self.mongo_collection_name].delete_one(
            {"_id": self._to_object_id(combo_id)}
        )
        return result.deleted_count > 0

    async def update_availability(self, combo_id: str, availability: bool) -> bool:
        """Update combo availability."""
        db = get_database()
        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(combo_id)},
            {"$set": {"availability": availability, "updatedAt": datetime.utcnow()}},
        )
        return result.modified_count > 0


# Singleton instance
combos_repo = ComboRepository()
