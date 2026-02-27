"""Branch Invitation repository for database operations."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from clients import get_database
from domain.models import BranchInvitation


class BranchInvitationRepository:
    collection_name = "branch_invitations"

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    # --- Query Methods ---

    async def get_by_code(self, code: str) -> Optional[BranchInvitation]:
        """Get invitation by code."""
        db = get_database()
        doc = await db[self.collection_name].find_one({"code": code.upper()})
        return BranchInvitation(**self._convert_id(doc)) if doc else None

    async def get_by_id(self, invitation_id: str) -> Optional[BranchInvitation]:
        """Get invitation by ID."""
        db = get_database()
        doc = await db[self.collection_name].find_one(self._build_id_query(invitation_id))
        return BranchInvitation(**self._convert_id(doc)) if doc else None

    async def get_by_business(self, business_id: str) -> List[BranchInvitation]:
        """Get all invitations for a business (for management UI)."""
        db = get_database()
        cursor = db[self.collection_name].find(
            {"businessId": self._to_object_id(business_id)}
        ).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [BranchInvitation(**self._convert_id(doc)) for doc in docs]

    async def get_active_by_business(self, business_id: str) -> List[BranchInvitation]:
        """Get active (pending) invitations for a business."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "businessId": self._to_object_id(business_id),
            "status": "pending"
        }).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [BranchInvitation(**self._convert_id(doc)) for doc in docs]

    async def get_by_branch(self, branch_id: str) -> List[BranchInvitation]:
        """Get all invitations for a specific branch."""
        db = get_database()
        cursor = db[self.collection_name].find({
            "branchId": self._to_object_id(branch_id),
            "invitationType": "branch"
        }).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [BranchInvitation(**self._convert_id(doc)) for doc in docs]

    async def get_by_user(self, user_id: str) -> List[BranchInvitation]:
        """Get all invitations used by a specific user (audit trail)."""
        db = get_database()
        cursor = db[self.collection_name].find(
            {"usedBy": self._to_object_id(user_id)}
        ).sort("usedAt", -1)
        docs = await cursor.to_list(length=None)
        return [BranchInvitation(**self._convert_id(doc)) for doc in docs]

    # --- Create Method ---

    async def create(self, invitation: BranchInvitation) -> BranchInvitation:
        """Create a new invitation."""
        db = get_database()
        doc = invitation.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["businessId"] = self._to_object_id(doc["businessId"])
        if doc.get("branchId") is not None:
            doc["branchId"] = self._to_object_id(doc["branchId"])
        doc["createdBy"] = self._to_object_id(doc["createdBy"])
        if doc.get("usedBy") is not None:
            doc["usedBy"] = self._to_object_id(doc["usedBy"])
        await db[self.collection_name].insert_one(doc)
        return invitation

    # --- Update Methods ---

    async def mark_as_used(
        self,
        code: str,
        user_id: str,
        access_expires_at: Optional[datetime] = None
    ) -> Optional[BranchInvitation]:
        """
        Mark invitation as used by a specific user.
        This is atomic and prevents double-use via status check.

        Args:
            code: Invitation code
            user_id: ID of user redeeming the code
            access_expires_at: When the access granted by this code expires (None = indefinido)

        Returns:
            Updated invitation if successful, None if already used or invalid
        """
        db = get_database()
        now = datetime.utcnow()

        result = await db[self.collection_name].find_one_and_update(
            {
                "code": code.upper(),
                "status": "pending"  # Only update if still pending (atomic check)
            },
            {
                "$set": {
                    "status": "used",
                    "usedBy": self._to_object_id(user_id),
                    "usedAt": now,
                    "accessExpiresAt": access_expires_at
                }
            },
            return_document=True
        )

        return BranchInvitation(**self._convert_id(result)) if result else None

    async def revoke(self, invitation_id: str) -> Optional[BranchInvitation]:
        """Revoke an invitation (manual cancellation)."""
        db = get_database()
        result = await db[self.collection_name].find_one_and_update(
            self._build_id_query(invitation_id),
            {"$set": {"status": "revoked"}},
            return_document=True
        )

        return BranchInvitation(**self._convert_id(result)) if result else None

    # --- Helper Methods ---

    async def get_expired_branch_invitations(self) -> List[BranchInvitation]:
        """
        Get all branch-type invitations where access has expired.
        Used by expiration worker to clean up access.
        """
        db = get_database()
        now = datetime.utcnow()

        cursor = db[self.collection_name].find({
            "invitationType": "branch",
            "status": "used",
            "accessExpiresAt": {"$lte": now, "$ne": None}
        })

        docs = await cursor.to_list(length=None)
        return [BranchInvitation(**self._convert_id(doc)) for doc in docs]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string if needed."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    @staticmethod
    def _build_id_query(invitation_id: str) -> Dict[str, Any]:
        """Build a query that works with string or ObjectId IDs."""
        ids = [BranchInvitationRepository._to_object_id(invitation_id)]
        try:
            ids.append(ObjectId(invitation_id))
        except Exception:
            pass
        if len(ids) == 1:
            return {"_id": ids[0]}
        return {"_id": {"$in": ids}}


# Singleton instance
branch_invitations_repo = BranchInvitationRepository()
