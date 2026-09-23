"""QvaPay como proveedor de pago digital (Grupo A).

Adaptador delgado sobre el QvaPayService ya existente — create_invoice/
handle_webhook no se tocan, solo se envuelven para cumplir el contrato
DigitalPaymentProvider y así poder colgar de initiate_payment() en vez de la
mutación GraphQL dedicada initiateQvapayPayment.

Nota importante: QvaPayService.handle_webhook sigue siendo la fuente de
verdad del pago (crea el payout al negocio, marca la orden pagada
directamente) — ese comportamiento no cambia. Lo que SÍ es nuevo es que
initiate() ahora crea un PaymentAttempt real (antes QvaPay ni pasaba por
PaymentAttempt). handle_confirmed_event() todavía no sincroniza el status de
ese PaymentAttempt a COMPLETED — hay que cerrar ese punto antes de activar
este proveedor (ver ENABLED_PAYMENT_METHOD_TYPES).
"""

import logging
from typing import Any, Dict, Optional

from domain.payments import PaymentAttempt, PaymentAttemptStatus
from services.payments.providers.base import DigitalPaymentProvider
from services.payments.qvapay_service import QvaPayService

logger = logging.getLogger(__name__)


class QvaPayProvider(DigitalPaymentProvider):
    method_code = "qvapay"

    def __init__(self):
        from repositories.payout_repository import payouts_repo
        from repositories.qvapay_repository import qvapay_invoices_repo

        self._service = QvaPayService(
            invoices_repo=qvapay_invoices_repo,
            payouts_repo=payouts_repo,
        )

    async def initiate(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str,
    ) -> PaymentAttempt:
        try:
            result = await self._service.create_invoice(
                order_id=str(order.get("_id")),
                branch_id=str(order.get("branchId")),
                business_id=str(order.get("businessId")),
                amount=payment_attempt.totalAmount,
                description=f"Pedido #{order.get('orderNumber', '')}",
            )
        except RuntimeError as e:
            logger.error(f"QvaPay error: {e}")
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = str(e)
            return payment_attempt

        payment_attempt.providerReference = result.transaction_uuid
        payment_attempt.providerPayload = {"paymentUrl": result.url}
        payment_attempt.status = PaymentAttemptStatus.PROCESSING
        return payment_attempt

    async def handle_confirmed_event(
        self, event: Dict[str, Any]
    ) -> Optional[PaymentAttempt]:
        """event = {"payload": QvaPayWebhookPayload, "signature_header": Optional[str]}."""
        await self._service.handle_webhook(
            event["payload"], event.get("signature_header")
        )
        return None
