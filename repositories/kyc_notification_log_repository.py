"""Repository for KYC notification delivery logs."""

from datetime import datetime
from typing import Any

from bson import ObjectId

from clients import get_database


class KycNotificationLogRepository:
    collection_name = "kyc_notification_logs"

    @staticmethod
    def _to_object_id(value: Any):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    def _collection(self):
        return get_database()[self.collection_name]

    async def create(
        self,
        *,
        kyc_verification_id: str,
        merchant_id: str,
        event_type: str,
        channel: str,
        status: str = "pending",
        attempts: int = 0,
        last_error: str = None,
    ) -> str:
        now = datetime.utcnow()
        doc = {
            "_id": ObjectId(),
            "kycVerificationId": self._to_object_id(kyc_verification_id),
            "merchantId": self._to_object_id(merchant_id),
            "eventType": event_type,
            "channel": channel,
            "status": status,
            "attempts": attempts,
            "lastError": last_error,
            "sentAt": now if status == "sent" else None,
            "createdAt": now,
            "updatedAt": now,
        }
        await self._collection().insert_one(doc)
        return str(doc["_id"])


kyc_notification_logs_repo = KycNotificationLogRepository()
