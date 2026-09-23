"""TronDealer (USDT) como proveedor de pago digital (Grupo A).

Adaptador delgado sobre el TronDealerService ya existente — misma nota que
qvapay_provider.py: create_wallet/handle_webhook no se tocan, y
handle_confirmed_event todavía no sincroniza el PaymentAttempt creado por
initiate() a COMPLETED (pendiente antes de activar este proveedor).
"""

import logging
from typing import Any, Dict, Optional

from domain.payments import PaymentAttempt, PaymentAttemptStatus
from services.payments.providers.base import DigitalPaymentProvider
from services.payments.trondealer_service import TronDealerService

logger = logging.getLogger(__name__)


class TronDealerProvider(DigitalPaymentProvider):
    # El campo PaymentMethod.method en Mongo para USDT/TronDealer es "usdt"
    # (confirmado vía OrderDetailViewModel/OrderPermissionPolicy en iOS — el
    # backend no sembra ni valida este valor en ningún otro lugar), no
    # "trondealer" (ese es solo el nombre del proveedor/servicio).
    method_code = "usdt"

    def __init__(self):
        from repositories.payout_repository import payouts_repo
        from repositories.trondealer_repository import trondealer_wallets_repo

        self._service = TronDealerService(
            wallets_repo=trondealer_wallets_repo,
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
            result = await self._service.create_wallet(
                order_id=str(order.get("_id")),
                branch_id=str(order.get("branchId")),
                business_id=str(order.get("businessId")),
                expected_amount=payment_attempt.totalAmount,
            )
        except RuntimeError as e:
            logger.error(f"TronDealer error: {e}")
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = str(e)
            return payment_attempt

        payment_attempt.providerReference = result.address
        payment_attempt.providerPayload = {
            "address": result.address,
            "token": result.token,
            "network": result.network,
        }
        payment_attempt.status = PaymentAttemptStatus.PROCESSING
        return payment_attempt

    async def handle_confirmed_event(
        self, event: Dict[str, Any]
    ) -> Optional[PaymentAttempt]:
        """event = {"raw_body": bytes, "signature_header": Optional[str],
        "client_ip": Optional[str], "payload": TronDealerWebhookPayload}."""
        await self._service.handle_webhook(
            raw_body=event["raw_body"],
            signature_header=event.get("signature_header"),
            client_ip=event.get("client_ip"),
            payload=event["payload"],
        )
        return None
