"""Repository for QvaPay invoice records."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients import get_database
from domain.crypto_payments import QvaPayInvoice, QvaPayInvoiceStatus


class QvaPayRepository:
    """CRUD and lookup operations for QvaPay invoices."""

    @property
    def _col(self):
        return get_database()["qvapay_invoices"]

    async def create(self, invoice: QvaPayInvoice) -> QvaPayInvoice:
        doc = invoice.model_dump(by_alias=True)
        doc["_id"] = ObjectId()
        await self._col.insert_one(doc)
        return QvaPayInvoice(**doc)

    async def get_by_id(self, invoice_id: str) -> Optional[QvaPayInvoice]:
        doc = await self._col.find_one({"_id": ObjectId(invoice_id)})
        return QvaPayInvoice(**doc) if doc else None

    async def get_by_order_id(self, order_id: str) -> Optional[QvaPayInvoice]:
        doc = await self._col.find_one({"orderId": ObjectId(order_id)})
        return QvaPayInvoice(**doc) if doc else None

    async def get_by_transaction_uuid(self, transaction_uuid: str) -> Optional[QvaPayInvoice]:
        """Lookup by QvaPay transaction_uuid — used for idempotency checks."""
        doc = await self._col.find_one({"transactionUuid": transaction_uuid})
        return QvaPayInvoice(**doc) if doc else None

    async def mark_completed(self, transaction_uuid: str) -> Optional[QvaPayInvoice]:
        """Mark invoice as completed idempotently; returns None if already completed."""
        now = datetime.utcnow()
        result = await self._col.find_one_and_update(
            {
                "transactionUuid": transaction_uuid,
                "status": QvaPayInvoiceStatus.PENDING,  # only update if still pending
            },
            {
                "$set": {
                    "status": QvaPayInvoiceStatus.COMPLETED,
                    "completedAt": now,
                    "webhookReceivedAt": now,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return QvaPayInvoice(**result) if result else None

    async def mark_failed(self, transaction_uuid: str) -> None:
        now = datetime.utcnow()
        await self._col.update_one(
            {"transactionUuid": transaction_uuid},
            {"$set": {"status": QvaPayInvoiceStatus.FAILED, "updatedAt": now}},
        )

    async def mark_cancelled(self, transaction_uuid: str) -> Optional[QvaPayInvoice]:
        """Mark invoice as cancelled; returns the updated invoice or None if not found."""
        now = datetime.utcnow()
        result = await self._col.find_one_and_update(
            {
                "transactionUuid": transaction_uuid,
                "status": QvaPayInvoiceStatus.PENDING,  # only cancel if still pending
            },
            {
                "$set": {
                    "status": QvaPayInvoiceStatus.CANCELLED,
                    "cancelledAt": now,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return QvaPayInvoice(**result) if result else None

    async def get_pending(self, limit: int = 100) -> List[QvaPayInvoice]:
        cursor = self._col.find(
            {"status": QvaPayInvoiceStatus.PENDING}
        ).sort("createdAt", 1).limit(limit)
        return [QvaPayInvoice(**doc) async for doc in cursor]


qvapay_invoices_repo = QvaPayRepository()
