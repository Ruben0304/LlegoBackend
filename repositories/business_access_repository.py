"""Business Access repository for database operations."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from clients import get_database
from models import BusinessAccess


class BusinessAccessRepository:
    collection_name = "business_access"

    # --- Query Methods ---

    async def get_by_id(self, access_id: str) -> Optional[BusinessAccess]:
        """Get business access by ID."""
        db = get_database()
        doc = await db[self.collection_name].find_one(self._build_id_query(access_id))
        return BusinessAccess(**self._convert_id(doc)) if doc else None

    async def get_by_user_and_business(
        self,
        user_id: str,
        business_id: str
    ) -> Optional[BusinessAccess]:
        """
        Get active business access for a specific user and business.
        Returns only if isActive=True.
        """
        db = get_database()
        doc = await db[self.collection_name].find_one({
            "userId": user_id,
            "businessId": business_id,
            "isActive": True
        })
        return BusinessAccess(**self._convert_id(doc)) if doc else None

    async def get_active_by_user(self, user_id: str) -> List[BusinessAccess]:
        """Get all active business accesses for a user."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "userId": user_id,
            "isActive": True
        }).sort("grantedAt", -1)
        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    async def get_active_by_business(self, business_id: str) -> List[BusinessAccess]:
        """Get all active business accesses for a business."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "businessId": business_id,
            "isActive": True
        }).sort("grantedAt", -1)
        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    async def get_by_business(self, business_id: str) -> List[BusinessAccess]:
        """Get all business accesses for a business (active and inactive)."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "businessId": business_id
        }).sort("grantedAt", -1)
        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    async def get_by_user(self, user_id: str) -> List[BusinessAccess]:
        """Get all business accesses for a user (active and inactive)."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "userId": user_id
        }).sort("grantedAt", -1)
        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    async def get_by_invitation(self, invitation_id: str) -> Optional[BusinessAccess]:
        """Get business access by invitation ID."""
        db = get_database()
        doc = await db[self.collection_name].find_one({"invitationId": invitation_id})
        return BusinessAccess(**self._convert_id(doc)) if doc else None

    # --- Create Method ---

    async def create(self, access: BusinessAccess) -> BusinessAccess:
        """Create a new business access record."""
        db = get_database()
        doc = access.model_dump(by_alias=True)
        await db[self.collection_name].insert_one(doc)
        return access

    # --- Update Methods ---

    async def revoke(self, access_id: str, revoked_by: str) -> Optional[BusinessAccess]:
        """
        Revoke a business access (manual cancellation).

        Args:
            access_id: ID of the business access to revoke
            revoked_by: ID of user who revoked it (usually business owner)

        Returns:
            Updated BusinessAccess if successful, None otherwise
        """
        db = get_database()
        now = datetime.utcnow()

        result = await db[self.collection_name].find_one_and_update(
            self._build_id_query(access_id),
            {
                "$set": {
                    "isActive": False,
                    "revokedAt": now,
                    "revokedBy": revoked_by
                }
            },
            return_document=True
        )

        return BusinessAccess(**self._convert_id(result)) if result else None

    # --- Cleanup Methods for Expiration Worker ---

    async def get_expired_accesses(self) -> List[BusinessAccess]:
        """
        Get all active business accesses that have expired.
        Used by expiration worker to clean up access.
        """
        db = get_database()
        now = datetime.utcnow()

        cursor = db[self.collection_name].find({
            "isActive": True,
            "expiresAt": {"$lte": now, "$ne": None}
        })

        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    async def mark_as_expired(self, access_id: str) -> Optional[BusinessAccess]:
        """
        Mark a business access as inactive because it expired.
        Called by expiration worker.
        """
        db = get_database()
        result = await db[self.collection_name].find_one_and_update(
            self._build_id_query(access_id),
            {"$set": {"isActive": False}},
            return_document=True
        )

        return BusinessAccess(**self._convert_id(result)) if result else None

    async def get_expiring_soon(self, days: int) -> List[BusinessAccess]:
        """
        Get active accesses that will expire within the specified number of days.
        Useful for sending expiration notifications.

        Args:
            days: Number of days in the future to check

        Returns:
            List of BusinessAccess expiring soon
        """
        db = get_database()
        now = datetime.utcnow()
        from datetime import timedelta
        future = now + timedelta(days=days)

        cursor = db[self.collection_name].find({
            "isActive": True,
            "expiresAt": {"$gte": now, "$lte": future, "$ne": None}
        })

        docs = await cursor.to_list(length=None)
        return [BusinessAccess(**self._convert_id(doc)) for doc in docs]

    # --- Helper Methods ---

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string if needed."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    @staticmethod
    def _build_id_query(access_id: str) -> Dict[str, Any]:
        """Build a query that works with string or ObjectId IDs."""
        ids = [access_id]
        try:
            ids.append(ObjectId(access_id))
        except Exception:
            pass
        if len(ids) == 1:
            return {"_id": ids[0]}
        return {"_id": {"$in": ids}}


# Singleton instance
business_access_repo = BusinessAccessRepository()
