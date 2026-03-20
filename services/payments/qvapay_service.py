"""QvaPay payment integration service.

Flow:
  1. create_invoice()  → calls POST https://api.qvapay.com/v2/create_invoice
                         saves QvaPayInvoice in DB, returns payment URL.
  2. handle_webhook()  → receives POST /api/v1/webhooks/qvapay
                         validates signature, deduplicates by transactionUuid,
                         marks order PAID, creates PendingPayout.
"""

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Optional

import httpx
from bson import ObjectId
from pydantic import BaseModel

from clients.mongodb_client import get_database
from core.config import settings
from domain.crypto_payments import PendingPayout, QvaPayInvoice, QvaPayInvoiceStatus
from repositories.qvapay_repository import QvaPayRepository
from repositories.payout_repository import PayoutRepository

logger = logging.getLogger(__name__)

QVAPAY_API_BASE = "https://api.qvapay.com/v2"


# ---------------------------------------------------------------------------
# Pydantic schemas for QvaPay API interaction
# ---------------------------------------------------------------------------


class QvaPayCreateInvoiceRequest(BaseModel):
    amount: float
    description: str
    remote_id: str
    webhook: Optional[str] = None
    expire_at: Optional[str] = None  # ISO 8601


class QvaPayCreateInvoiceResponse(BaseModel):
    app_id: str
    amount: float
    description: str
    remote_id: str
    transaction_uuid: str
    expire_at: Optional[str] = None
    url: str


class QvaPayWebhookPayload(BaseModel):
    """
    Webhook payload sent by QvaPay when a transaction changes status.
    Fields confirmed from QvaPay v2 docs.
    """
    transaction_uuid: str
    remote_id: str
    amount: float
    status: str          # "completed" | "pending" | "failed"
    description: Optional[str] = None
    app_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class QvaPayService:
    def __init__(
        self,
        invoices_repo: QvaPayRepository,
        payouts_repo: PayoutRepository,
    ):
        self._invoices = invoices_repo
        self._payouts = payouts_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_invoice(
        self,
        order_id: str,
        branch_id: str,
        business_id: str,
        amount: float,
        description: str,
        webhook_url: Optional[str] = None,
    ) -> QvaPayCreateInvoiceResponse:
        """
        Create a QvaPay invoice for an order.
        Returns the QvaPay response including the payment URL.
        """
        if not settings.qvapay_app_id or not settings.qvapay_app_secret:
            raise RuntimeError("QvaPay credentials not configured.")

        payload = {
            "amount": amount,
            "description": description,
            "remote_id": order_id,
        }
        if webhook_url:
            payload["webhook"] = webhook_url

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{QVAPAY_API_BASE}/create_invoice",
                json=payload,
                headers={
                    "app-id": settings.qvapay_app_id,
                    "app-secret": settings.qvapay_app_secret,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            logger.error(
                "QvaPay create_invoice failed order=%s status=%s body=%s",
                order_id,
                response.status_code,
                response.text,
            )
            raise RuntimeError(f"QvaPay API error: {response.status_code} {response.text}")

        data = response.json()
        invoice_resp = QvaPayCreateInvoiceResponse(**data)

        # Persist invoice
        expire_at: Optional[datetime] = None
        if invoice_resp.expire_at:
            try:
                expire_at = datetime.fromisoformat(invoice_resp.expire_at.replace("Z", "+00:00"))
            except ValueError:
                pass

        invoice = QvaPayInvoice(
            _id=ObjectId(),
            orderId=ObjectId(order_id),
            branchId=ObjectId(branch_id),
            businessId=ObjectId(business_id),
            transactionUuid=invoice_resp.transaction_uuid,
            remoteId=order_id,
            amount=amount,
            description=description,
            paymentUrl=invoice_resp.url,
            expireAt=expire_at,
            status=QvaPayInvoiceStatus.PENDING,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
        await self._invoices.create(invoice)

        logger.info(
            "QvaPay invoice created order=%s uuid=%s url=%s",
            order_id,
            invoice_resp.transaction_uuid,
            invoice_resp.url,
        )
        return invoice_resp

    async def handle_webhook(
        self,
        payload: QvaPayWebhookPayload,
        signature_header: Optional[str],
    ) -> bool:
        """
        Process an incoming QvaPay webhook.

        Returns True if the webhook was processed (new), False if it was a duplicate.
        Raises ValueError on invalid signature.
        """
        # 1. Validate signature
        self._verify_signature(payload.transaction_uuid, signature_header)

        # 2. Only act on "completed" events
        if payload.status != "completed":
            logger.info(
                "QvaPay webhook ignored — status=%s uuid=%s",
                payload.status,
                payload.transaction_uuid,
            )
            return False

        # 3. Idempotency: attempt to mark invoice as completed atomically
        invoice = await self._invoices.mark_completed(payload.transaction_uuid)
        if invoice is None:
            # Already processed or not found
            existing = await self._invoices.get_by_transaction_uuid(payload.transaction_uuid)
            if existing and existing.status == QvaPayInvoiceStatus.COMPLETED:
                logger.info(
                    "QvaPay duplicate webhook ignored uuid=%s", payload.transaction_uuid
                )
                return False
            logger.warning(
                "QvaPay webhook: invoice not found for uuid=%s", payload.transaction_uuid
            )
            return False

        logger.info(
            "QvaPay payment completed order=%s uuid=%s amount=%s",
            str(invoice.orderId),
            payload.transaction_uuid,
            payload.amount,
        )

        # 4. Mark order as PAID (same pattern as payments_service.py)
        db = get_database()
        await db.orders.update_one(
            {"_id": invoice.orderId},
            {
                "$set": {
                    "paymentStatus": "completed",
                    "paidAt": datetime.utcnow(),
                    "status": "pending_acceptance",
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

        # 5. Register pending payout
        payout = PendingPayout(
            _id=ObjectId(),
            orderId=invoice.orderId,
            branchId=invoice.branchId,
            businessId=invoice.businessId,
            amount=payload.amount,
            currency="usd",
            gateway="qvapay",
            externalTransactionId=payload.transaction_uuid,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
        await self._payouts.create(payout)

        logger.info(
            "PendingPayout created gateway=qvapay order=%s amount=%s",
            str(invoice.orderId),
            payload.amount,
        )
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _verify_signature(
        self, transaction_uuid: str, signature_header: Optional[str]
    ) -> None:
        """
        Verify the webhook signature sent by QvaPay.

        QvaPay sends an HMAC-SHA256 of the transaction_uuid signed with the
        app_secret in the X-QvaPay-Signature header.
        Skip verification if qvapay_webhook_secret is not configured (dev mode).
        """
        secret = settings.qvapay_webhook_secret
        if not secret:
            logger.debug("QvaPay webhook signature check skipped (no secret configured).")
            return

        if not signature_header:
            raise ValueError("Missing X-QvaPay-Signature header.")

        expected = hmac.new(
            secret.encode(),
            transaction_uuid.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature_header):
            raise ValueError("Invalid QvaPay webhook signature.")
