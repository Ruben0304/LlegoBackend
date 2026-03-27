"""Repository for cash KYC verifications."""

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from clients import get_database
from domain.kyc import KycVerification


class KycVerificationRepository:
    collection_name = "kyc_verifications"

    @staticmethod
    def _to_object_id(value: Any):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_model(doc: Dict[str, Any]) -> KycVerification:
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return KycVerification(**doc)

    def _collection(self):
        return get_database()[self.collection_name]

    async def create(self, verification: KycVerification) -> KycVerification:
        doc = verification.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        for field in [
            "paymentAttemptId",
            "orderId",
            "customerId",
            "merchantId",
            "branchId",
        ]:
            doc[field] = self._to_object_id(doc[field])
        await self._collection().insert_one(doc)
        return verification

    async def get_by_id(self, verification_id: str) -> Optional[KycVerification]:
        try:
            doc = await self._collection().find_one({"_id": ObjectId(verification_id)})
        except Exception:
            doc = await self._collection().find_one({"_id": verification_id})
        return self._doc_to_model(doc) if doc else None

    async def get_latest_by_payment_attempt(
        self, payment_attempt_id: str
    ) -> Optional[KycVerification]:
        doc = await self._collection().find_one(
            {"paymentAttemptId": self._to_object_id(payment_attempt_id)},
            sort=[("createdAt", -1)],
        )
        return self._doc_to_model(doc) if doc else None

    async def get_reusable_approved(
        self,
        customer_id: str,
        merchant_id: str,
        policy_version: str,
        now: Optional[datetime] = None,
    ) -> Optional[KycVerification]:
        now = now or datetime.utcnow()
        query = {
            "customerId": self._to_object_id(customer_id),
            "merchantId": self._to_object_id(merchant_id),
            "policyVersion": policy_version,
            "status": "approved",
            "forceReverify": {"$ne": True},
            "expiresAt": {"$gt": now},
        }
        doc = await self._collection().find_one(query, sort=[("approvedAt", -1)])
        return self._doc_to_model(doc) if doc else None

    async def get_latest_by_customer_merchant(
        self,
        *,
        customer_id: str,
        merchant_id: str,
        policy_version: Optional[str] = None,
    ) -> Optional[KycVerification]:
        query = {
            "customerId": self._to_object_id(customer_id),
            "merchantId": self._to_object_id(merchant_id),
        }
        if policy_version:
            query["policyVersion"] = policy_version
        doc = await self._collection().find_one(query, sort=[("createdAt", -1)])
        return self._doc_to_model(doc) if doc else None

    async def update_result(
        self,
        verification_id: str,
        *,
        status: str,
        verdict: Optional[str],
        confidence_score: Optional[float],
        reason_codes: Optional[list],
        extracted_signals: Optional[dict],
        model_version: Optional[str],
        evaluated_at: Optional[datetime],
        expires_at: Optional[datetime],
        last_error: Optional[str] = None,
    ) -> Optional[KycVerification]:
        update_data = {
            "status": status,
            "verdict": verdict,
            "confidenceScore": confidence_score,
            "reasonCodes": reason_codes or [],
            "extractedSignals": extracted_signals,
            "modelVersion": model_version,
            "evaluatedAt": evaluated_at,
            "expiresAt": expires_at,
            "updatedAt": datetime.utcnow(),
            "lastError": last_error,
        }
        if status == "approved":
            update_data["approvedAt"] = datetime.utcnow()

        try:
            doc = await self._collection().find_one_and_update(
                {"_id": ObjectId(verification_id)},
                {"$set": update_data},
                return_document=True,
            )
        except Exception:
            doc = await self._collection().find_one_and_update(
                {"_id": verification_id},
                {"$set": update_data},
                return_document=True,
            )

        return self._doc_to_model(doc) if doc else None

    async def increment_retry(
        self, verification_id: str, error: Optional[str]
    ) -> Optional[KycVerification]:
        try:
            doc = await self._collection().find_one_and_update(
                {"_id": ObjectId(verification_id)},
                {
                    "$inc": {"retryCount": 1},
                    "$set": {"lastError": error, "updatedAt": datetime.utcnow()},
                },
                return_document=True,
            )
        except Exception:
            doc = await self._collection().find_one_and_update(
                {"_id": verification_id},
                {
                    "$inc": {"retryCount": 1},
                    "$set": {"lastError": error, "updatedAt": datetime.utcnow()},
                },
                return_document=True,
            )
        return self._doc_to_model(doc) if doc else None


kyc_verifications_repo = KycVerificationRepository()


async def create_kyc_indexes():
    """Create MongoDB indexes for KYC collections."""
    db = get_database()
    verifications = db["kyc_verifications"]
    notifications = db["kyc_notification_logs"]
    audits = db["kyc_audit_events"]

    await verifications.create_index("idempotencyKey", unique=True)
    await verifications.create_index([("paymentAttemptId", 1), ("createdAt", -1)])
    await verifications.create_index(
        [("customerId", 1), ("merchantId", 1), ("status", 1), ("expiresAt", -1)]
    )
    await verifications.create_index(
        [("customerId", 1), ("merchantId", 1), ("policyVersion", 1), ("createdAt", -1)]
    )
    await verifications.create_index([("verificationSource", 1), ("createdAt", -1)])
    await verifications.create_index("correlationId")

    await notifications.create_index(
        [("kycVerificationId", 1), ("eventType", 1), ("channel", 1)]
    )
    await notifications.create_index([("status", 1), ("updatedAt", 1)])

    await audits.create_index([("entityType", 1), ("entityId", 1), ("createdAt", -1)])

    print("✓ KYC indexes created")
