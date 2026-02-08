"""Feedback repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from domain.models import Feedback


class FeedbackRepository:
    collection_name = "feedbacks"

    async def get_all(self) -> List[Feedback]:
        """Get all feedbacks."""
        db = get_database()
        cursor = db[self.collection_name].find()
        feedbacks = await cursor.to_list(length=None)
        return [Feedback(**self._convert_id(f)) for f in feedbacks]

    async def get_by_id(self, feedback_id: str) -> Optional[Feedback]:
        """Get feedback by ID."""
        db = get_database()
        try:
            object_id = ObjectId(feedback_id)
        except Exception:
            object_id = feedback_id
        feedback = await db[self.collection_name].find_one({"_id": object_id})
        return Feedback(**self._convert_id(feedback)) if feedback else None

    async def get_by_user(self, user_id: str) -> List[Feedback]:
        """Get all feedbacks by a specific user."""
        db = get_database()
        cursor = db[self.collection_name].find({"userId": user_id})
        feedbacks = await cursor.to_list(length=None)
        return [Feedback(**self._convert_id(f)) for f in feedbacks]

    async def get_by_type(self, feedback_type: str) -> List[Feedback]:
        """Get feedbacks by type (BUG, FEATURE_REQUEST, IMPROVEMENT)."""
        db = get_database()
        cursor = db[self.collection_name].find({"type": feedback_type})
        feedbacks = await cursor.to_list(length=None)
        return [Feedback(**self._convert_id(f)) for f in feedbacks]

    async def get_by_status(self, status: str) -> List[Feedback]:
        """Get feedbacks by status (PENDING, IN_REVIEW, RESOLVED, DISMISSED)."""
        db = get_database()
        cursor = db[self.collection_name].find({"status": status})
        feedbacks = await cursor.to_list(length=None)
        return [Feedback(**self._convert_id(f)) for f in feedbacks]

    async def create(self, feedback_data: Dict[str, Any]) -> Feedback:
        """Create a new feedback."""
        db = get_database()
        result = await db[self.collection_name].insert_one(feedback_data)
        feedback_data["_id"] = str(result.inserted_id)
        return Feedback(**feedback_data)

    async def update(self, feedback_id: str, updates: Dict[str, Any]) -> Optional[Feedback]:
        """Update a feedback."""
        db = get_database()
        try:
            object_id = ObjectId(feedback_id)
        except Exception:
            object_id = feedback_id

        # Always update updatedAt timestamp
        from datetime import datetime
        updates["updatedAt"] = datetime.utcnow()

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return Feedback(**self._convert_id(result)) if result else None

    async def delete(self, feedback_id: str) -> bool:
        """Delete a feedback."""
        db = get_database()
        try:
            object_id = ObjectId(feedback_id)
        except Exception:
            object_id = feedback_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
