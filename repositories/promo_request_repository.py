"""Promo request repository for database operations."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.promos import PromoRequest


class PromoRequestRepository:
    """Persistence for promos submitted from the customer app.

    Read/write is driven by the administrative app; the customer app only ever
    calls :meth:`create`.
    """

    collection_name = "promo_requests"

    async def create(self, data: Dict[str, Any]) -> PromoRequest:
        """Store a new submission with status ``pending``."""
        db = get_database()
        now = datetime.now(timezone.utc)
        doc = {
            **data,
            "status": "pending",
            "createdAt": now,
            "updatedAt": now,
        }
        result = await db[self.collection_name].insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return PromoRequest(**doc)

    async def get_by_id(self, request_id: str) -> Optional[PromoRequest]:
        """Get a promo request by ID."""
        db = get_database()
        doc = await db[self.collection_name].find_one({"_id": self._object_id(request_id)})
        return PromoRequest(**self._convert_id(doc)) if doc else None

    async def list_by_status(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[PromoRequest]:
        """List submissions newest first, optionally filtered by status."""
        db = get_database()
        query: Dict[str, Any] = {"status": status} if status else {}
        cursor = (
            db[self.collection_name]
            .find(query)
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [PromoRequest(**self._convert_id(d)) for d in docs]

    async def count_by_status(self, status: Optional[str] = None) -> int:
        """Count submissions, optionally filtered by status."""
        db = get_database()
        query: Dict[str, Any] = {"status": status} if status else {}
        return await db[self.collection_name].count_documents(query)

    async def set_status(
        self,
        request_id: str,
        status: str,
        reviewed_by_user_id: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> Optional[PromoRequest]:
        """Approve or reject a submission from the administrative app."""
        db = get_database()
        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "status": status,
            "reviewedAt": now,
            "updatedAt": now,
            "rejectionReason": rejection_reason,
        }
        if reviewed_by_user_id:
            updates["reviewedByUserId"] = reviewed_by_user_id

        doc = await db[self.collection_name].find_one_and_update(
            {"_id": self._object_id(request_id)},
            {"$set": updates},
            return_document=True,
        )
        return PromoRequest(**self._convert_id(doc)) if doc else None

    @staticmethod
    def _object_id(value: str) -> Any:
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
