"""Promotional video repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
from clients import get_database
from domain.models import PromotionalVideo


class PromotionalVideoRepository:
    collection_name = "promotional_videos"

    async def get_all(self) -> List[PromotionalVideo]:
        """Get all promotional videos ordered by order field."""
        db = get_database()
        cursor = db[self.collection_name].find().sort("order", 1)
        videos = await cursor.to_list(length=None)
        return [PromotionalVideo(**self._convert_id(video)) for video in videos]

    async def get_by_id(self, video_id: str) -> Optional[PromotionalVideo]:
        """Get a promotional video by ID."""
        db = get_database()
        try:
            object_id = ObjectId(video_id)
        except Exception:
            object_id = video_id
        video = await db[self.collection_name].find_one({"_id": object_id})
        return PromotionalVideo(**self._convert_id(video)) if video else None

    async def get_active(self) -> List[PromotionalVideo]:
        """Get all active promotional videos ordered by order field."""
        db = get_database()
        cursor = db[self.collection_name].find({"isActive": True}).sort("order", 1)
        videos = await cursor.to_list(length=None)
        return [PromotionalVideo(**self._convert_id(video)) for video in videos]

    async def get_by_app_target(self, app_target: str) -> List[PromotionalVideo]:
        """Get promotional videos by app target (customer, merchant, both)."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "isActive": True,
            "$or": [
                {"appTarget": app_target},
                {"appTarget": "both"}
            ]
        }).sort("order", 1)
        videos = await cursor.to_list(length=None)
        return [PromotionalVideo(**self._convert_id(video)) for video in videos]

    async def get_by_branch(self, branch_id: str) -> List[PromotionalVideo]:
        """Get promotional videos uploaded by a specific branch."""
        db = get_database()
        try:
            branch_object_id = ObjectId(branch_id)
        except Exception:
            branch_object_id = branch_id
        cursor = db[self.collection_name].find({
            "branchId": {"$in": [branch_object_id, branch_id]}
        }).sort("order", 1)
        videos = await cursor.to_list(length=None)
        return [PromotionalVideo(**self._convert_id(video)) for video in videos]

    async def create(self, video_data: Dict[str, Any]) -> PromotionalVideo:
        """Create a new promotional video."""
        db = get_database()
        video_data["createdAt"] = datetime.utcnow()
        video_data["updatedAt"] = None

        # Store branchId as ObjectId when provided so branch queries match
        branch_id = video_data.get("branchId")
        if branch_id:
            try:
                video_data["branchId"] = ObjectId(branch_id)
            except Exception:
                pass

        result = await db[self.collection_name].insert_one(video_data)
        video_data["_id"] = str(result.inserted_id)
        return PromotionalVideo(**self._convert_id(video_data))

    async def update(self, video_id: str, updates: Dict[str, Any]) -> Optional[PromotionalVideo]:
        """Update a promotional video."""
        db = get_database()
        try:
            object_id = ObjectId(video_id)
        except Exception:
            object_id = video_id

        updates["updatedAt"] = datetime.utcnow()

        if "branchId" in updates and updates["branchId"]:
            try:
                updates["branchId"] = ObjectId(updates["branchId"])
            except Exception:
                pass

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return PromotionalVideo(**self._convert_id(result)) if result else None

    async def delete(self, video_id: str) -> bool:
        """Delete a promotional video."""
        db = get_database()
        try:
            object_id = ObjectId(video_id)
        except Exception:
            object_id = video_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def toggle_active(self, video_id: str) -> Optional[PromotionalVideo]:
        """Toggle the isActive status of a promotional video."""
        video = await self.get_by_id(video_id)
        if not video:
            return None

        new_status = not video.isActive
        return await self.update(video_id, {"isActive": new_status})

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
