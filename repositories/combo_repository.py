"""Combo repository for database operations."""

import uuid
from datetime import datetime
from typing import List, Optional

from clients import get_database
from domain.models import Combo


class ComboRepository:
    """Repository for Combo CRUD operations."""

    mongo_collection_name = "combos"

    async def create(self, combo_data: dict) -> Combo:
        """Create a new combo."""
        db = get_database()

        # Generate ID and timestamps
        combo_data["_id"] = str(uuid.uuid4())
        combo_data["createdAt"] = datetime.utcnow()
        combo_data["updatedAt"] = datetime.utcnow()

        # Generate IDs for slots
        for slot in combo_data.get("slots", []):
            if "id" not in slot:
                slot["id"] = str(uuid.uuid4())

        await db[self.mongo_collection_name].insert_one(combo_data)
        return Combo(**combo_data)

    async def get_by_id(self, combo_id: str) -> Optional[Combo]:
        """Get combo by ID."""
        db = get_database()
        doc = await db[self.mongo_collection_name].find_one({"_id": combo_id})

        if doc:
            return Combo(**doc)
        return None

    async def get_by_branch(
        self, branch_id: str, available_only: bool = True
    ) -> List[Combo]:
        """Get all combos for a branch."""
        db = get_database()
        query = {"branchId": branch_id}

        if available_only:
            query["availability"] = True

        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)

        return [Combo(**doc) for doc in docs]

    async def get_all(self, available_only: bool = False) -> List[Combo]:
        """Get all combos."""
        db = get_database()
        query = {}

        if available_only:
            query["availability"] = True

        cursor = db[self.mongo_collection_name].find(query).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)

        return [Combo(**doc) for doc in docs]

    async def update(self, combo_id: str, update_data: dict) -> Optional[Combo]:
        """Update a combo."""
        db = get_database()

        # Add updated timestamp
        update_data["updatedAt"] = datetime.utcnow()

        # Generate IDs for new slots if needed
        if "slots" in update_data:
            for slot in update_data["slots"]:
                if "id" not in slot:
                    slot["id"] = str(uuid.uuid4())

        result = await db[self.mongo_collection_name].update_one(
            {"_id": combo_id}, {"$set": update_data}
        )

        if result.modified_count > 0:
            return await self.get_by_id(combo_id)
        return None

    async def delete(self, combo_id: str) -> bool:
        """Delete a combo."""
        db = get_database()
        result = await db[self.mongo_collection_name].delete_one({"_id": combo_id})
        return result.deleted_count > 0

    async def update_availability(self, combo_id: str, availability: bool) -> bool:
        """Update combo availability."""
        db = get_database()
        result = await db[self.mongo_collection_name].update_one(
            {"_id": combo_id},
            {"$set": {"availability": availability, "updatedAt": datetime.utcnow()}},
        )
        return result.modified_count > 0


# Singleton instance
combos_repo = ComboRepository()
