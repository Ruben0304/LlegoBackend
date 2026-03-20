"""Repository for pending payout records."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients import get_database
from domain.crypto_payments import PayoutStatus, PendingPayout


class PayoutRepository:
    """CRUD and lookup operations for pending payouts."""

    @property
    def _col(self):
        return get_database()["pending_payouts"]

    async def create(self, payout: PendingPayout) -> PendingPayout:
        doc = payout.model_dump(by_alias=True)
        doc["_id"] = ObjectId()
        await self._col.insert_one(doc)
        return PendingPayout(**doc)

    async def get_by_id(self, payout_id: str) -> Optional[PendingPayout]:
        doc = await self._col.find_one({"_id": ObjectId(payout_id)})
        return PendingPayout(**doc) if doc else None

    async def get_by_order_id(self, order_id: str) -> Optional[PendingPayout]:
        doc = await self._col.find_one({"orderId": ObjectId(order_id)})
        return PendingPayout(**doc) if doc else None

    async def get_pending(
        self,
        gateway: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PendingPayout]:
        """List payouts with payoutStatus=pending, optionally filtered by gateway."""
        query: dict = {"payoutStatus": PayoutStatus.PENDING}
        if gateway:
            query["gateway"] = gateway
        cursor = (
            self._col.find(query)
            .sort("createdAt", 1)
            .skip(offset)
            .limit(limit)
        )
        return [PendingPayout(**doc) async for doc in cursor]

    async def confirm(self, payout_id: str, confirmed_by: str, notes: Optional[str] = None) -> Optional[PendingPayout]:
        """Mark a payout as confirmed (liquidated manually)."""
        now = datetime.utcnow()
        update: dict = {
            "payoutStatus": PayoutStatus.CONFIRMED,
            "confirmedBy": ObjectId(confirmed_by),
            "confirmedAt": now,
            "updatedAt": now,
        }
        if notes:
            update["notes"] = notes
        result = await self._col.find_one_and_update(
            {"_id": ObjectId(payout_id), "payoutStatus": PayoutStatus.PENDING},
            {"$set": update},
            return_document=True,
        )
        return PendingPayout(**result) if result else None

    async def cancel(self, payout_id: str) -> Optional[PendingPayout]:
        now = datetime.utcnow()
        result = await self._col.find_one_and_update(
            {"_id": ObjectId(payout_id), "payoutStatus": PayoutStatus.PENDING},
            {"$set": {"payoutStatus": PayoutStatus.CANCELLED, "updatedAt": now}},
            return_document=True,
        )
        return PendingPayout(**result) if result else None

    async def count_pending(self, gateway: Optional[str] = None) -> int:
        query: dict = {"payoutStatus": PayoutStatus.PENDING}
        if gateway:
            query["gateway"] = gateway
        return await self._col.count_documents(query)


payouts_repo = PayoutRepository()
