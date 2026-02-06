"""Tutorial repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from clients import get_database
from models import Tutorial


class TutorialRepository:
    collection_name = "tutorials"

    async def get_all(self) -> List[Tutorial]:
        """Get all tutorials."""
        db = get_database()
        cursor = db[self.collection_name].find().sort("order", 1)
        tutorials = await cursor.to_list(length=None)
        return [Tutorial(**self._convert_id(tutorial)) for tutorial in tutorials]

    async def get_by_id(self, tutorial_id: str) -> Optional[Tutorial]:
        """Get a tutorial by ID."""
        db = get_database()
        try:
            object_id = ObjectId(tutorial_id)
        except Exception:
            object_id = tutorial_id
        tutorial = await db[self.collection_name].find_one({"_id": object_id})
        return Tutorial(**self._convert_id(tutorial)) if tutorial else None

    async def get_active(self) -> List[Tutorial]:
        """Get all active tutorials ordered by order field."""
        db = get_database()
        cursor = db[self.collection_name].find({"isActive": True}).sort("order", 1)
        tutorials = await cursor.to_list(length=None)
        return [Tutorial(**self._convert_id(tutorial)) for tutorial in tutorials]

    async def get_by_app_target(self, app_target: str) -> List[Tutorial]:
        """Get tutorials by app target (customer, merchant, both)."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "isActive": True,
            "$or": [
                {"appTarget": app_target},
                {"appTarget": "both"}
            ]
        }).sort("order", 1)
        tutorials = await cursor.to_list(length=None)
        return [Tutorial(**self._convert_id(tutorial)) for tutorial in tutorials]

    async def get_by_tags(self, tags: List[str]) -> List[Tutorial]:
        """Get tutorials that have any of the provided tags."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "isActive": True,
            "tags": {"$in": tags}
        }).sort("order", 1)
        tutorials = await cursor.to_list(length=None)
        return [Tutorial(**self._convert_id(tutorial)) for tutorial in tutorials]

    async def search(self, query: str) -> List[Tutorial]:
        """Search tutorials by title or description."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "isActive": True,
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"tags": {"$regex": query, "$options": "i"}}
            ]
        }).sort("order", 1)
        tutorials = await cursor.to_list(length=None)
        return [Tutorial(**self._convert_id(tutorial)) for tutorial in tutorials]

    async def create(self, tutorial_data: Dict[str, Any]) -> Tutorial:
        """Create a new tutorial."""
        db = get_database()
        tutorial_data["createdAt"] = datetime.utcnow()
        tutorial_data["updatedAt"] = None

        result = await db[self.collection_name].insert_one(tutorial_data)
        tutorial_data["_id"] = str(result.inserted_id)
        return Tutorial(**tutorial_data)

    async def update(self, tutorial_id: str, updates: Dict[str, Any]) -> Optional[Tutorial]:
        """Update a tutorial."""
        db = get_database()
        try:
            object_id = ObjectId(tutorial_id)
        except Exception:
            object_id = tutorial_id

        updates["updatedAt"] = datetime.utcnow()

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return Tutorial(**self._convert_id(result)) if result else None

    async def delete(self, tutorial_id: str) -> bool:
        """Delete a tutorial."""
        db = get_database()
        try:
            object_id = ObjectId(tutorial_id)
        except Exception:
            object_id = tutorial_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def toggle_active(self, tutorial_id: str) -> Optional[Tutorial]:
        """Toggle the isActive status of a tutorial."""
        db = get_database()
        try:
            object_id = ObjectId(tutorial_id)
        except Exception:
            object_id = tutorial_id

        # Get current tutorial to toggle its status
        tutorial = await self.get_by_id(tutorial_id)
        if not tutorial:
            return None

        new_status = not tutorial.isActive
        return await self.update(tutorial_id, {"isActive": new_status})

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
