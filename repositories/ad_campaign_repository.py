"""Ad campaign repository for database operations."""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from bson import ObjectId

from clients import get_database
from domain.ads import AdCampaign


class AdCampaignRepository:
    collection_name = "ad_campaigns"

    def _col(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def create(self, data: Dict[str, Any]) -> AdCampaign:
        """Create a new campaign. Stores owner/business/branch ids as ObjectId."""
        data = dict(data)
        data.setdefault("createdAt", datetime.utcnow())
        data["updatedAt"] = None
        for key in ("businessId", "branchId", "ownerId"):
            if data.get(key):
                data[key] = self._to_object_id(data[key])

        result = await self._col().insert_one(data)
        data["_id"] = str(result.inserted_id)
        return AdCampaign(**self._convert_id(data))

    async def get_by_id(self, campaign_id: str) -> Optional[AdCampaign]:
        doc = await self._col().find_one({"_id": self._to_object_id(campaign_id)})
        return AdCampaign(**self._convert_id(doc)) if doc else None

    async def get_by_owner(self, owner_id: str) -> List[AdCampaign]:
        cursor = self._col().find(
            {"ownerId": {"$in": [self._to_object_id(owner_id), owner_id]}}
        ).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [AdCampaign(**self._convert_id(d)) for d in docs]

    async def get_by_business(self, business_id: str) -> List[AdCampaign]:
        cursor = self._col().find(
            {"businessId": {"$in": [self._to_object_id(business_id), business_id]}}
        ).sort("createdAt", -1)
        docs = await cursor.to_list(length=None)
        return [AdCampaign(**self._convert_id(d)) for d in docs]

    async def list_by_status(self, status: str) -> List[AdCampaign]:
        cursor = self._col().find({"status": status}).sort("createdAt", 1)
        docs = await cursor.to_list(length=None)
        return [AdCampaign(**self._convert_id(d)) for d in docs]

    async def list_pending_review(self) -> List[AdCampaign]:
        """Moderation queue: not-yet-approved campaigns awaiting an admin.

        Includes unpaid ones (``pending_payment``) so an admin can admit a
        campaign even before it is paid.
        """
        query = {
            "approved": {"$ne": True},
            "status": {"$in": ["pending_payment", "pending_review"]},
        }
        cursor = self._col().find(query).sort("createdAt", 1)
        docs = await cursor.to_list(length=None)
        return [AdCampaign(**self._convert_id(d)) for d in docs]

    async def list_active_for_feed(
        self,
        placement: str,
        branch_ids: Iterable[str],
        limit: int = 20,
    ) -> List[AdCampaign]:
        """Feed-visible campaigns of a placement whose branch is in ``branch_ids``.

        Visibility gate is the ``approved`` boolean (set by an admin), decoupled
        from payment. A campaign must also have an exported photo, be inside its
        [startAt, endAt] window, and not be paused/ended.
        """
        now = datetime.utcnow()
        oid_branches: List[Any] = []
        for bid in branch_ids:
            oid_branches.append(self._to_object_id(bid))
            oid_branches.append(bid)

        query = {
            "placement": placement,
            "approved": True,
            "creativeImagePath": {"$nin": [None, ""]},
            "status": {"$nin": ["paused", "ended"]},
            "branchId": {"$in": oid_branches},
            "$and": [
                {"$or": [{"startAt": None}, {"startAt": {"$lte": now}}]},
                {"$or": [{"endAt": None}, {"endAt": {"$gte": now}}]},
            ],
        }
        cursor = self._col().find(query).sort("createdAt", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [AdCampaign(**self._convert_id(d)) for d in docs]

    async def update(self, campaign_id: str, updates: Dict[str, Any]) -> Optional[AdCampaign]:
        updates = dict(updates)
        updates["updatedAt"] = datetime.utcnow()
        doc = await self._col().find_one_and_update(
            {"_id": self._to_object_id(campaign_id)},
            {"$set": updates},
            return_document=True,
        )
        return AdCampaign(**self._convert_id(doc)) if doc else None

    async def increment_metric(self, campaign_id: str, field: str, amount: int = 1) -> None:
        if field not in ("impressions", "clicks"):
            return
        await self._col().update_one(
            {"_id": self._to_object_id(campaign_id)},
            {"$inc": {field: amount}},
        )

    async def delete(self, campaign_id: str) -> bool:
        result = await self._col().delete_one({"_id": self._to_object_id(campaign_id)})
        return result.deleted_count > 0
