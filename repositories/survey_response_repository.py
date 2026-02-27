"""SurveyResponse repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from domain.models import SurveyResponse


class SurveyResponseRepository:
    collection_name = "survey_responses"

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def get_all(self) -> List[SurveyResponse]:
        """Get all survey responses."""
        db = get_database()
        cursor = db[self.collection_name].find()
        responses = await cursor.to_list(length=None)
        return [SurveyResponse(**self._convert_id(r)) for r in responses]

    async def get_by_id(self, response_id: str) -> Optional[SurveyResponse]:
        """Get survey response by ID."""
        db = get_database()
        try:
            object_id = ObjectId(response_id)
        except Exception:
            object_id = response_id
        response = await db[self.collection_name].find_one({"_id": object_id})
        return SurveyResponse(**self._convert_id(response)) if response else None

    async def get_by_survey(self, survey_id: str) -> List[SurveyResponse]:
        """Get all responses for a specific survey."""
        db = get_database()
        cursor = db[self.collection_name].find({"surveyId": self._to_object_id(survey_id)})
        responses = await cursor.to_list(length=None)
        return [SurveyResponse(**self._convert_id(r)) for r in responses]

    async def get_by_user(self, user_id: str) -> List[SurveyResponse]:
        """Get all responses by a specific user."""
        db = get_database()
        cursor = db[self.collection_name].find({"userId": self._to_object_id(user_id)})
        responses = await cursor.to_list(length=None)
        return [SurveyResponse(**self._convert_id(r)) for r in responses]

    async def get_by_survey_and_user(
        self,
        survey_id: str,
        user_id: str
    ) -> Optional[SurveyResponse]:
        """Check if user has already responded to a survey."""
        db = get_database()
        response = await db[self.collection_name].find_one({
            "surveyId": self._to_object_id(survey_id),
            "userId": self._to_object_id(user_id)
        })
        return SurveyResponse(**self._convert_id(response)) if response else None

    async def create(self, response_data: Dict[str, Any]) -> SurveyResponse:
        """Create a new survey response."""
        db = get_database()
        response_doc = dict(response_data)
        response_doc["surveyId"] = self._to_object_id(response_doc["surveyId"])
        response_doc["userId"] = self._to_object_id(response_doc["userId"])
        result = await db[self.collection_name].insert_one(response_doc)
        response_doc["_id"] = result.inserted_id
        return SurveyResponse(**response_doc)

    async def delete(self, response_id: str) -> bool:
        """Delete a survey response."""
        db = get_database()
        try:
            object_id = ObjectId(response_id)
        except Exception:
            object_id = response_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
