"""Draft order repository for AI-created pending orders."""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from clients import get_database
from domain.models import DraftOrder, DraftOrderItem


class DraftOrderRepository:
    """Repository for managing draft orders created by AI assistant."""

    collection_name = "draft_orders"

    async def create_draft(
        self,
        session_id: str,
        customer_id: str,
        branch_id: str,
        business_id: str,
        items: List[Dict[str, Any]],
        subtotal: float,
        delivery_fee: float,
        total: float,
        currency: str = "USD",
        delivery_address: Optional[Dict[str, Any]] = None,
        payment_method_id: Optional[str] = None,
        branch_avatar: Optional[str] = None
    ) -> DraftOrder:
        """
        Create a draft order.

        Args:
            session_id: User ID from JWT
            customer_id: Customer user ID (same as session_id)
            branch_id: Branch ID where order is placed
            business_id: Business ID
            items: List of order items
            subtotal: Order subtotal
            delivery_fee: Delivery fee
            total: Total amount
            currency: Currency code (default: USD)
            delivery_address: Delivery address dict
            payment_method_id: Payment method ID
            branch_avatar: Branch avatar URL (denormalized for quick access)

        Returns:
            DraftOrder object
        """
        db = get_database()

        # Auto-expire after 1 hour
        expires_at = datetime.utcnow() + timedelta(hours=1)

        new_draft = {
            "sessionId": session_id,
            "customerId": customer_id,
            "branchId": branch_id,
            "businessId": business_id,
            "branchAvatar": branch_avatar,
            "items": items,
            "subtotal": subtotal,
            "deliveryFee": delivery_fee,
            "total": total,
            "currency": currency,
            "deliveryAddress": delivery_address,
            "paymentMethodId": payment_method_id,
            "status": "pending_confirmation",
            "createdAt": datetime.utcnow(),
            "expiresAt": expires_at
        }

        result = await db[self.collection_name].insert_one(new_draft)
        new_draft["_id"] = result.inserted_id

        return DraftOrder(**self._convert_id(new_draft))

    async def get_by_id(self, draft_id: str) -> Optional[DraftOrder]:
        """
        Get a draft order by ID.

        Args:
            draft_id: Draft order ID

        Returns:
            DraftOrder object or None
        """
        db = get_database()
        from bson import ObjectId

        try:
            draft = await db[self.collection_name].find_one({"_id": ObjectId(draft_id)})
            return DraftOrder(**self._convert_id(draft)) if draft else None
        except Exception:
            return None

    async def get_pending_by_session(self, session_id: str) -> List[DraftOrder]:
        """
        Get all pending draft orders for a session.

        Args:
            session_id: User ID from JWT

        Returns:
            List of DraftOrder objects
        """
        db = get_database()

        cursor = db[self.collection_name].find({
            "sessionId": session_id,
            "status": "pending_confirmation",
            "expiresAt": {"$gt": datetime.utcnow()}  # Not expired
        }).sort("createdAt", -1)

        drafts = await cursor.to_list(length=100)
        return [DraftOrder(**self._convert_id(draft)) for draft in drafts]

    async def update_status(
        self,
        draft_id: str,
        status: str
    ) -> Optional[DraftOrder]:
        """
        Update draft order status.

        Args:
            draft_id: Draft order ID
            status: New status ("pending_confirmation", "confirmed", "cancelled")

        Returns:
            Updated DraftOrder or None
        """
        db = get_database()
        from bson import ObjectId

        try:
            result = await db[self.collection_name].find_one_and_update(
                {"_id": ObjectId(draft_id)},
                {"$set": {"status": status}},
                return_document=True
            )
            return DraftOrder(**self._convert_id(result)) if result else None
        except Exception:
            return None

    async def delete_expired(self) -> int:
        """
        Delete expired draft orders.

        Returns:
            Number of deleted drafts
        """
        db = get_database()
        result = await db[self.collection_name].delete_many({
            "expiresAt": {"$lt": datetime.utcnow()}
        })
        return result.deleted_count

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
