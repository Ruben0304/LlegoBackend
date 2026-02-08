"""Survey repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from domain.models import Survey


class SurveyRepository:
    collection_name = "surveys"

    async def get_all(self) -> List[Survey]:
        """Get all surveys."""
        db = get_database()
        cursor = db[self.collection_name].find()
        surveys = await cursor.to_list(length=None)
        return [Survey(**self._convert_id(s)) for s in surveys]

    async def get_by_id(self, survey_id: str) -> Optional[Survey]:
        """Get survey by ID."""
        db = get_database()
        try:
            object_id = ObjectId(survey_id)
        except Exception:
            object_id = survey_id
        survey = await db[self.collection_name].find_one({"_id": object_id})
        return Survey(**self._convert_id(survey)) if survey else None

    async def get_active(self) -> List[Survey]:
        """Get all active surveys."""
        db = get_database()
        cursor = db[self.collection_name].find({"isActive": True})
        surveys = await cursor.to_list(length=None)
        return [Survey(**self._convert_id(s)) for s in surveys]

    async def create(self, survey_data: Dict[str, Any]) -> Survey:
        """Create a new survey."""
        db = get_database()
        result = await db[self.collection_name].insert_one(survey_data)
        survey_data["_id"] = str(result.inserted_id)
        return Survey(**survey_data)

    async def update(self, survey_id: str, updates: Dict[str, Any]) -> Optional[Survey]:
        """Update a survey."""
        db = get_database()
        try:
            object_id = ObjectId(survey_id)
        except Exception:
            object_id = survey_id

        # Always update updatedAt timestamp
        from datetime import datetime
        updates["updatedAt"] = datetime.utcnow()

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return Survey(**self._convert_id(result)) if result else None

    async def deactivate(self, survey_id: str) -> Optional[Survey]:
        """Deactivate a survey."""
        return await self.update(survey_id, {"isActive": False})

    async def delete(self, survey_id: str) -> bool:
        """Delete a survey."""
        db = get_database()
        try:
            object_id = ObjectId(survey_id)
        except Exception:
            object_id = survey_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
