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
from services.payments.qvapay_transfer_service import qvapay_transfer_service

logger = logging.getLogger(__name__)

QVAPAY_API_BASE = "https://api.qvapay.com/v2"


# ---------------------------------------------------------------------------
# Pydantic schemas for QvaPay API interaction
# ---------------------------------------------------------------------------


class QvaPayProduct(BaseModel):
    name: str
    price: float
    quantity: int = 1


class QvaPayCreateInvoiceRequest(BaseModel):
    amount: float
    description: str
    remote_id: str
    webhook: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    products: Optional[list[QvaPayProduct]] = None
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
    Based on real QvaPay v2 webhook data.
    """
    transaction_uuid: str
    remote_id: str
    amount: str  # Viene como string, ej: "1" o "10.50"
    status: str  # "paid" | "pending" | "failed"
    signed: bool  # IMPORTANTE: debe ser true para procesar
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    
    @property
    def amount_float(self) -> float:
        """Convierte amount de string a float."""
        return float(self.amount)


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
        products: Optional[list[dict]] = None,
    ) -> QvaPayCreateInvoiceResponse:
        """
        Create a QvaPay invoice for an order.
        Returns the QvaPay response including the payment URL.
        
        If QVAPAY_TEST_AMOUNT is set to a value > 0, that amount will be used
        instead of the real amount for testing purposes.
        """
        if not settings.qvapay_app_id or not settings.qvapay_app_secret:
            raise RuntimeError("QvaPay credentials not configured.")

        # Use test amount if configured, otherwise use real amount
        invoice_amount = amount
        if settings.qvapay_test_amount > 0:
            invoice_amount = settings.qvapay_test_amount
            logger.info(
                "Using QvaPay test amount: $%.2f (real amount: $%.2f) for order=%s",
                invoice_amount,
                amount,
                order_id,
            )

        payload = {
            "amount": invoice_amount,
            "description": description,
            "remote_id": order_id,
        }
        if webhook_url:
            payload["webhook"] = webhook_url
        
        # Add success and cancel URLs if base URL is configured
        if settings.qvapay_base_url:
            payload["success_url"] = f"{settings.qvapay_base_url}/api/v1/qvapay/success"
            payload["cancel_url"] = f"{settings.qvapay_base_url}/api/v1/qvapay/cancel"
        
        # Add products if provided
        if products:
            payload["products"] = products

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

        # Persist invoice with the REAL amount (not test amount)
        # This ensures the database reflects the actual order amount
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
            amount=amount,  # Store REAL amount, not test amount
            description=description,
            paymentUrl=invoice_resp.url,
            expireAt=expire_at,
            status=QvaPayInvoiceStatus.PENDING,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
        await self._invoices.create(invoice)

        logger.info(
            "QvaPay invoice created order=%s uuid=%s url=%s invoice_amount=$%.2f real_amount=$%.2f",
            order_id,
            invoice_resp.transaction_uuid,
            invoice_resp.url,
            invoice_amount,
            amount,
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
        Raises ValueError on invalid signature or unsigned webhook.
        """
        # 1. Validate signature (if configured)
        self._verify_signature(payload.transaction_uuid, signature_header)
        
        # 2. CRITICAL: Verify signed field
        if not payload.signed:
            logger.warning(
                "QvaPay webhook rejected — signed=false uuid=%s",
                payload.transaction_uuid,
            )
            raise ValueError("Webhook not signed by QvaPay (signed=false)")

        # 3. Only act on "paid" events (QvaPay usa "paid", no "completed")
        if payload.status != "paid":
            logger.info(
                "QvaPay webhook ignored — status=%s uuid=%s",
                payload.status,
                payload.transaction_uuid,
            )
            return False

        # 4. Idempotency: attempt to mark invoice as completed atomically
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

        # Convertir amount de string a float
        amount_float = payload.amount_float

        logger.info(
            "QvaPay payment completed order=%s uuid=%s amount=%s",
            str(invoice.orderId),
            payload.transaction_uuid,
            amount_float,
        )

        # 5. Mark order as PAID (same pattern as payments_service.py)
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

        # 6. Register pending payout
        payout = PendingPayout(
            _id=ObjectId(),
            orderId=invoice.orderId,
            branchId=invoice.branchId,
            businessId=invoice.businessId,
            amount=amount_float,
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
            amount_float,
        )
        
        # 7. Attempt automatic transfer to business QvaPay account
        await self._attempt_auto_transfer(payout, invoice)
        
        return True

    async def handle_success_callback(self, transaction_uuid: str) -> dict:
        """
        Handle success callback when user completes payment.
        Returns dict with 'found' boolean and invoice info.
        """
        invoice = await self._invoices.get_by_transaction_uuid(transaction_uuid)
        
        if not invoice:
            logger.warning(
                "QvaPay success callback: invoice not found uuid=%s", transaction_uuid
            )
            return {"found": False, "invoice": None}
        
        logger.info(
            "QvaPay success callback order=%s uuid=%s status=%s",
            str(invoice.orderId),
            transaction_uuid,
            invoice.status,
        )
        
        return {
            "found": True,
            "invoice": invoice,
            "order_id": str(invoice.orderId),
            "status": invoice.status,
        }

    async def handle_cancel_callback(self, transaction_uuid: str) -> dict:
        """
        Handle cancel callback when user cancels payment.
        Marks invoice as cancelled and cancels the order.
        Returns dict with 'cancelled' boolean.
        """
        invoice = await self._invoices.get_by_transaction_uuid(transaction_uuid)
        
        if not invoice:
            logger.warning(
                "QvaPay cancel callback: invoice not found uuid=%s", transaction_uuid
            )
            return {"cancelled": False, "found": False}
        
        # Only cancel if still pending
        if invoice.status == QvaPayInvoiceStatus.PENDING:
            # Mark invoice as cancelled
            await self._invoices.mark_cancelled(transaction_uuid)
            
            # Cancel the order
            db = get_database()
            await db.orders.update_one(
                {"_id": invoice.orderId},
                {
                    "$set": {
                        "paymentStatus": "cancelled",
                        "status": "cancelled",
                        "updatedAt": datetime.utcnow(),
                    }
                },
            )
            
            logger.info(
                "QvaPay payment cancelled order=%s uuid=%s",
                str(invoice.orderId),
                transaction_uuid,
            )
            return {"cancelled": True, "found": True, "order_id": str(invoice.orderId)}
        
        logger.info(
            "QvaPay cancel callback ignored — already processed uuid=%s status=%s",
            transaction_uuid,
            invoice.status,
        )
        return {"cancelled": False, "found": True, "status": invoice.status}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _attempt_auto_transfer(
        self, payout: PendingPayout, invoice: QvaPayInvoice
    ) -> None:
        """
        Attempt automatic transfer to business QvaPay account.
        If successful, marks payout as confirmed.
        If fails, logs error and leaves payout as pending for manual processing.
        """
        # Check if auto-transfer is enabled
        if not settings.qvapay_platform_pin:
            logger.info(
                "QvaPay auto-transfer disabled (no PIN configured) payout=%s",
                str(payout.id),
            )
            return
        
        try:
            # Fetch branch to get qvapayUsername
            db = get_database()
            branch = await db.branches.find_one({"_id": invoice.branchId})
            
            if not branch:
                logger.warning(
                    "Branch not found for auto-transfer payout=%s branch_id=%s",
                    str(payout.id),
                    str(invoice.branchId),
                )
                return
            
            qvapay_username = branch.get("qvapayUsername")
            if not qvapay_username:
                logger.warning(
                    "Branch has no qvapayUsername configured payout=%s branch=%s",
                    str(payout.id),
                    branch.get("name", "unknown"),
                )
                return
            
            business_name = branch.get("name", "Negocio")
            
            # Attempt transfer
            logger.info(
                "Attempting automatic QvaPay transfer payout=%s to=%s amount=%s",
                str(payout.id),
                qvapay_username,
                payout.amount,
            )
            
            transfer_result = await qvapay_transfer_service.transfer_to_business(
                amount=payout.amount,
                qvapay_username=qvapay_username,
                description=f"Pago por orden {str(payout.orderId)[:8]} - {business_name}",
                pin=settings.qvapay_platform_pin,
            )
            
            # Mark payout as confirmed with transfer details
            transfer_notes = (
                f"Transferencia automática QvaPay exitosa\n"
                f"Transaction UUID: {transfer_result.transaction}\n"
                f"Destinatario: {qvapay_username}\n"
                f"Monto: ${payout.amount:.2f}"
            )
            
            confirmed_payout = await self._payouts.confirm(
                payout_id=str(payout.id),
                confirmed_by=str(ObjectId()),  # System user
                notes=transfer_notes,
            )
            
            if confirmed_payout:
                logger.info(
                    "QvaPay auto-transfer successful payout=%s transaction=%s to=%s",
                    str(payout.id),
                    transfer_result.transaction,
                    qvapay_username,
                )
            else:
                logger.error(
                    "Failed to mark payout as confirmed after successful transfer payout=%s",
                    str(payout.id),
                )
                
        except Exception as exc:
            # Log error but don't fail the webhook processing
            # Payout remains pending for manual processing
            logger.error(
                "QvaPay auto-transfer failed payout=%s error=%s",
                str(payout.id),
                str(exc),
                exc_info=True,
            )

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
