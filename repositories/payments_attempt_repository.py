"""Payment attempt repository for database operations."""

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.payments import PaymentAttempt, PaymentAttemptStatus


class PaymentAttemptRepository:
    """Repository for payment attempt operations."""

    collection_name = "payment_attempts"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _doc_to_payment_attempt(doc: dict) -> PaymentAttempt:
        """Convert MongoDB document to PaymentAttempt model."""
        doc["_id"] = str(doc["_id"])
        return PaymentAttempt(**doc)

    async def create(self, payment_attempt: PaymentAttempt) -> PaymentAttempt:
        """Create a new payment attempt."""
        collection = self._get_collection()
        doc = payment_attempt.model_dump(by_alias=True)
        doc["_id"] = self._to_object_id(doc["_id"])
        doc["orderId"] = self._to_object_id(doc["orderId"])
        doc["paymentMethodId"] = self._to_object_id(doc["paymentMethodId"])
        if doc.get("deliveryPersonId") is not None:
            doc["deliveryPersonId"] = self._to_object_id(doc["deliveryPersonId"])
        if doc.get("latestKycVerificationId") is not None:
            doc["latestKycVerificationId"] = self._to_object_id(
                doc["latestKycVerificationId"]
            )
        await collection.insert_one(doc)
        return payment_attempt

    async def get_by_id(self, attempt_id: str) -> Optional[PaymentAttempt]:
        """Get payment attempt by ID."""
        collection = self._get_collection()
        try:
            doc = await collection.find_one({"_id": ObjectId(attempt_id)})
        except Exception:
            doc = await collection.find_one({"_id": attempt_id})
        return self._doc_to_payment_attempt(doc) if doc else None

    async def get_by_order_id(self, order_id: str) -> List[PaymentAttempt]:
        """Get all payment attempts for an order."""
        collection = self._get_collection()
        cursor = collection.find({"orderId": self._to_object_id(order_id)}).sort(
            "createdAt", -1
        )
        return [self._doc_to_payment_attempt(doc) async for doc in cursor]

    async def get_active_by_order_id(self, order_id: str) -> Optional[PaymentAttempt]:
        """Get the active (non-final) payment attempt for an order."""
        collection = self._get_collection()
        final_statuses = [
            PaymentAttemptStatus.COMPLETED.value,
            PaymentAttemptStatus.FAILED.value,
            PaymentAttemptStatus.EXPIRED.value,
            PaymentAttemptStatus.CANCELLED.value,
            PaymentAttemptStatus.REFUNDED.value,
        ]
        doc = await collection.find_one(
            {
                "orderId": self._to_object_id(order_id),
                "status": {"$nin": final_statuses},
            }
        )
        return self._doc_to_payment_attempt(doc) if doc else None

    async def get_by_stripe_payment_intent(
        self, payment_intent_id: str
    ) -> Optional[PaymentAttempt]:
        """Get payment attempt by Stripe Payment Intent ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"stripePaymentIntentId": payment_intent_id})
        return self._doc_to_payment_attempt(doc) if doc else None

    async def update_status(
        self, attempt_id: str, status: PaymentAttemptStatus, **extra_fields
    ) -> Optional[PaymentAttempt]:
        """Update payment attempt status and optional extra fields."""
        collection = self._get_collection()
        update_data = {
            "status": status.value,
            "updatedAt": datetime.utcnow(),
            **extra_fields,
        }

        # Handle completion timestamps
        if status == PaymentAttemptStatus.COMPLETED:
            update_data["completedAt"] = datetime.utcnow()
        elif status == PaymentAttemptStatus.FAILED:
            update_data["failedAt"] = datetime.utcnow()

        try:
            result = await collection.find_one_and_update(
                {"_id": ObjectId(attempt_id)},
                {"$set": update_data},
                return_document=True,
            )
        except Exception:
            result = await collection.find_one_and_update(
                {"_id": attempt_id},
                {"$set": update_data},
                return_document=True,
            )

        return self._doc_to_payment_attempt(result) if result else None

    async def set_proof(
        self, attempt_id: str, proof_url: Optional[str] = None
    ) -> Optional[PaymentAttempt]:
        """Set proof URL and mark customer confirmed."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.AWAITING_BUSINESS,
            proofUrl=proof_url,
            customerConfirmedAt=datetime.utcnow(),
        )

    async def confirm_business_received(
        self, attempt_id: str
    ) -> Optional[PaymentAttempt]:
        """Mark that business confirmed payment received."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.COMPLETED,
            businessConfirmedAt=datetime.utcnow(),
        )

    async def confirm_delivery_cash(
        self, attempt_id: str, delivery_person_id: str
    ) -> Optional[PaymentAttempt]:
        """Mark that delivery person confirmed cash received."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.COMPLETED,
            deliveryPersonConfirmedAt=datetime.utcnow(),
            deliveryPersonId=delivery_person_id,
        )

    async def dispute(self, attempt_id: str, reason: str) -> Optional[PaymentAttempt]:
        """Mark payment as disputed."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.DISPUTED,
            disputeReason=reason,
        )

    async def request_refund(
        self, attempt_id: str, reason: str
    ) -> Optional[PaymentAttempt]:
        """Mark payment as refund requested."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.REFUND_REQUESTED,
            refundRequestedAt=datetime.utcnow(),
            refundReason=reason,
        )

    async def complete_refund(
        self, attempt_id: str, refund_amount: float, transaction_id: str
    ) -> Optional[PaymentAttempt]:
        """Mark refund as completed."""
        return await self.update_status(
            attempt_id,
            PaymentAttemptStatus.REFUNDED,
            refundedAt=datetime.utcnow(),
            refundAmount=refund_amount,
            refundTransactionId=transaction_id,
        )

    async def set_wallet_transaction(
        self,
        attempt_id: str,
        wallet_transaction_id: str,
        business_wallet_transaction_id: str,
        commission_transaction_id: str,
    ) -> Optional[PaymentAttempt]:
        """Set wallet transaction IDs after successful wallet payment."""
        collection = self._get_collection()
        try:
            result = await collection.find_one_and_update(
                {"_id": ObjectId(attempt_id)},
                {
                    "$set": {
                        "walletTransactionId": wallet_transaction_id,
                        "businessWalletTransactionId": business_wallet_transaction_id,
                        "commissionTransactionId": commission_transaction_id,
                        "updatedAt": datetime.utcnow(),
                    }
                },
                return_document=True,
            )
        except Exception:
            result = await collection.find_one_and_update(
                {"_id": attempt_id},
                {
                    "$set": {
                        "walletTransactionId": wallet_transaction_id,
                        "businessWalletTransactionId": business_wallet_transaction_id,
                        "commissionTransactionId": commission_transaction_id,
                        "updatedAt": datetime.utcnow(),
                    }
                },
                return_document=True,
            )

        return self._doc_to_payment_attempt(result) if result else None

    async def update_kyc_state(
        self,
        attempt_id: str,
        *,
        kyc_required: bool,
        kyc_eval_status: str,
        cash_coverage_status: str,
        latest_kyc_verification_id: Optional[str] = None,
        kyc_failure_code: Optional[str] = None,
    ) -> Optional[PaymentAttempt]:
        """Update KYC and coverage fields for a payment attempt."""
        update_data = {
            "kycRequired": kyc_required,
            "kycEvalStatus": kyc_eval_status,
            "cashCoverageStatus": cash_coverage_status,
            "kycDecisionAt": datetime.utcnow(),
            "kycFailureCode": kyc_failure_code,
            "updatedAt": datetime.utcnow(),
        }
        if latest_kyc_verification_id is not None:
            update_data["latestKycVerificationId"] = self._to_object_id(
                latest_kyc_verification_id
            )

        collection = self._get_collection()
        try:
            result = await collection.find_one_and_update(
                {"_id": ObjectId(attempt_id)},
                {"$set": update_data},
                return_document=True,
            )
        except Exception:
            result = await collection.find_one_and_update(
                {"_id": attempt_id},
                {"$set": update_data},
                return_document=True,
            )
        return self._doc_to_payment_attempt(result) if result else None

    async def get_expired(self) -> List[PaymentAttempt]:
        """Get all expired payment attempts that need to be marked as expired."""
        collection = self._get_collection()
        now = datetime.utcnow()
        cursor = collection.find(
            {
                "status": {
                    "$in": [
                        PaymentAttemptStatus.PENDING.value,
                        PaymentAttemptStatus.AWAITING_PROOF.value,
                        PaymentAttemptStatus.AWAITING_BUSINESS.value,
                        PaymentAttemptStatus.AWAITING_KYC.value,
                    ]
                },
                "expiresAt": {"$lte": now, "$ne": None},
            }
        )
        return [self._doc_to_payment_attempt(doc) async for doc in cursor]

    async def get_by_customer(
        self, customer_id: str, limit: int = 20, offset: int = 0
    ) -> List[PaymentAttempt]:
        """Get payment attempts for a customer (via orders)."""
        # This requires a join with orders collection
        # For now, we'll implement a simpler version
        db = get_database()
        orders_collection = db["orders"]

        # Get customer's order IDs
        order_ids = await orders_collection.distinct(
            "_id", {"customerId": self._to_object_id(customer_id)}
        )
        collection = self._get_collection()
        cursor = (
            collection.find({"orderId": {"$in": order_ids}})
            .sort("createdAt", -1)
            .skip(offset)
            .limit(limit)
        )

        return [self._doc_to_payment_attempt(doc) async for doc in cursor]

    async def list_filtered(
        self,
        *,
        order_ids: Optional[List[Any]] = None,
        payment_method_id: Optional[str] = None,
        status_in: Optional[List[str]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[PaymentAttempt], int]:
        """
        List payment attempts with optional filters and pagination.

        Notes:
        - order_ids should be raw Mongo IDs (ObjectId or str), not coerced here.
        - status_in should contain string enum values (e.g. "pending", "completed").
        """
        collection = self._get_collection()
        query: Dict[str, Any] = {}

        if order_ids is not None:
            # If caller supplies an empty list, return empty fast.
            if not order_ids:
                return [], 0
            query["orderId"] = {"$in": order_ids}

        if payment_method_id:
            query["paymentMethodId"] = self._to_object_id(payment_method_id)

        if status_in:
            query["status"] = {"$in": status_in}

        if from_date or to_date:
            query.setdefault("createdAt", {})
            if from_date:
                query["createdAt"]["$gte"] = from_date
            if to_date:
                query["createdAt"]["$lte"] = to_date

        total = await collection.count_documents(query)
        cursor = (
            collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
        )
        attempts = [self._doc_to_payment_attempt(doc) async for doc in cursor]
        return attempts, total


async def create_payment_indexes():
    """Create MongoDB indexes for payment attempts collection."""
    db = get_database()
    collection = db["payment_attempts"]

    await collection.create_index("orderId")
    await collection.create_index("stripePaymentIntentId", sparse=True)
    await collection.create_index([("status", 1), ("expiresAt", 1)])
    await collection.create_index("createdAt")
    await collection.create_index([("kycEvalStatus", 1), ("createdAt", -1)])
    await collection.create_index("latestKycVerificationId", sparse=True)

    print("✓ Payment attempt indexes created")


# Repository instance
payment_attempts_repo = PaymentAttemptRepository()
