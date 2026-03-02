"""Showcase repository for database operations."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.models import Showcase


class ShowcaseRepository:
    """Repository for Showcase CRUD operations."""

    mongo_collection_name = "showcases"

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    @staticmethod
    def _normalize_items(items: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if items is None:
            return None

        normalized: List[Dict[str, Any]] = []
        for item in items:
            normalized_item = dict(item)
            if not normalized_item.get("id"):
                normalized_item["id"] = str(uuid.uuid4())
            normalized.append(normalized_item)
        return normalized

    @classmethod
    def _normalize_showcase_doc(cls, showcase_data: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(showcase_data)
        doc["_id"] = cls._to_object_id(doc.get("_id", ObjectId()))
        doc["branchId"] = cls._to_object_id(doc.get("branchId"))
        if "items" in doc:
            doc["items"] = cls._normalize_items(doc.get("items"))
        return doc

    async def create(self, showcase_data: Dict[str, Any]) -> Showcase:
        """Create a new showcase."""
        db = get_database()
        now = datetime.utcnow()

        doc = self._normalize_showcase_doc(showcase_data)
        doc["createdAt"] = now
        doc["updatedAt"] = now

        await db[self.mongo_collection_name].insert_one(doc)
        return Showcase(**doc)

    async def get_by_id(self, showcase_id: str) -> Optional[Showcase]:
        """Get showcase by ID."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one(
            {"_id": self._to_object_id(showcase_id)}
        )
        return Showcase(**doc) if doc else None

    async def get_by_branch(
        self, branch_id: str, active_only: bool = True
    ) -> List[Showcase]:
        """Get showcases by branch."""
        db = get_database()
        query: Dict[str, Any] = {"branchId": self._to_object_id(branch_id)}
        if active_only:
            query["isActive"] = True

        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [Showcase(**doc) for doc in docs]

    async def get_all(self, active_only: bool = False) -> List[Showcase]:
        """Get all showcases."""
        db = get_database()
        query: Dict[str, Any] = {"isActive": True} if active_only else {}
        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [Showcase(**doc) for doc in docs]

    async def update(
        self, showcase_id: str, update_data: Dict[str, Any]
    ) -> Optional[Showcase]:
        """Update a showcase."""
        db = get_database()

        normalized_update = dict(update_data)
        if "branchId" in normalized_update:
            normalized_update["branchId"] = self._to_object_id(
                normalized_update["branchId"]
            )
        if "items" in normalized_update:
            normalized_update["items"] = self._normalize_items(normalized_update["items"])

        normalized_update["updatedAt"] = datetime.utcnow()

        result = await db[self.mongo_collection_name].find_one_and_update(
            {"_id": self._to_object_id(showcase_id)},
            {"$set": normalized_update},
            return_document=True,
        )
        return Showcase(**result) if result else None

    async def delete(self, showcase_id: str) -> bool:
        """Delete a showcase."""
        db = get_database()
        result = await db[self.mongo_collection_name].delete_one(
            {"_id": self._to_object_id(showcase_id)}
        )
        return result.deleted_count > 0

    async def update_availability(self, showcase_id: str, is_active: bool) -> bool:
        """Toggle showcase availability."""
        db = get_database()
        result = await db[self.mongo_collection_name].update_one(
            {"_id": self._to_object_id(showcase_id)},
            {"$set": {"isActive": is_active, "updatedAt": datetime.utcnow()}},
        )
        return result.modified_count > 0


showcases_repo = ShowcaseRepository()
