"""Stripe as a Grupo A digital payment provider.

Lógica movida tal cual desde services/payments_service.py
(_create_stripe_payment_intent, handle_stripe_webhook,
_process_stripe_payment_completion, _process_stripe_refund) — mismo
comportamiento, solo reubicada detrás del contrato DigitalPaymentProvider.
"""

import asyncio
import functools
import logging
from datetime import datetime
from typing import Any, Dict

import stripe
from bson import ObjectId

from clients.mongodb_client import get_database
from core.config import settings
from domain.payments import PaymentAttempt, PaymentAttemptStatus
from repositories.payments_attempt_repository import payment_attempts_repo
from services.payments import support as payments_support
from services.payments.providers.base import DigitalPaymentProvider

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


class StripeProvider(DigitalPaymentProvider):
    method_code = "stripe"

    async def initiate(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str,
    ) -> PaymentAttempt:
        try:
            amount_cents = int(payment_attempt.totalAmount * 100)

            intent = await asyncio.to_thread(
                functools.partial(
                    stripe.PaymentIntent.create,
                    amount=amount_cents,
                    currency=payment_attempt.currency,
                    description=f"Pedido #{order.get('orderNumber', '')} - Llego",
                    metadata={
                        "user_id": user_id,
                        "order_id": str(order.get("_id")),
                        "payment_attempt_id": payment_attempt.id,
                        "type": "order_payment",
                    },
                    automatic_payment_methods={"enabled": True},
                )
            )

            payment_attempt.providerReference = intent.id
            payment_attempt.providerPayload = {"clientSecret": intent.client_secret}
            # Compat: poblar también los campos legacy (ver domain/payments.py).
            payment_attempt.stripePaymentIntentId = intent.id
            payment_attempt.stripeClientSecret = intent.client_secret
            payment_attempt.status = PaymentAttemptStatus.PROCESSING

            logger.info(
                f"Created Stripe Payment Intent: {intent.id} for order {order.get('_id')}"
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = f"Error de Stripe: {str(e)}"

        return payment_attempt

    async def handle_confirmed_event(self, event: Dict[str, Any]) -> PaymentAttempt:
        """event = {"payment_intent_id": str, "event_type": str}."""
        payment_intent_id = event["payment_intent_id"]
        event_type = event["event_type"]

        attempt = await payment_attempts_repo.get_by_stripe_payment_intent(
            payment_intent_id
        )
        if not attempt:
            logger.warning(f"No payment attempt found for PI: {payment_intent_id}")
            return None

        if event_type == "payment_intent.succeeded":
            updated = await payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.COMPLETED,
            )

            order = await payments_support.get_order(attempt.orderId)
            if order:
                await self._process_payment_completion(attempt, order)
                await payments_support.complete_order_payment(
                    attempt.orderId, attempt.id
                )

            return updated

        elif event_type == "payment_intent.payment_failed":
            return await payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.FAILED,
                failedReason="Pago rechazado por Stripe",
            )

        return attempt

    async def _process_payment_completion(self, attempt: PaymentAttempt, order: dict):
        """Credita el wallet interno de Llego tras un pago Stripe exitoso."""
        db = get_database()
        now = datetime.utcnow()

        amount_to_business = attempt.subtotal + attempt.deliveryFee
        commission = attempt.commissionAmount
        currency = attempt.currency

        branch_id = order.get("branchId")
        await db.branches.update_one(
            {"_id": payments_support.to_object_id(branch_id)},
            {"$inc": {f"wallet.{currency}": amount_to_business}},
        )

        if commission > 0:
            await db.platform.update_one(
                {"_id": "platform"},
                {
                    "$inc": {
                        f"wallet.{currency}": commission,
                        "totalCommissionsCollected": commission
                        if currency == "usd"
                        else 0,
                    }
                },
            )

        business_tx = {
            "_id": ObjectId(),
            "fromOwnerId": "stripe",
            "fromOwnerType": "external",
            "toOwnerId": payments_support.to_object_id(order.get("branchId")),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "stripe_payment",
            "status": "completed",
            "description": f"Pago Stripe pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "stripePaymentIntentId": attempt.providerReference,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        if commission > 0:
            commission_tx = {
                "_id": ObjectId(),
                "fromOwnerId": "stripe",
                "fromOwnerType": "external",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission",
                "status": "completed",
                "description": f"Comisión Stripe pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": attempt.id,
                },
                "createdAt": now,
                "completedAt": now,
            }
            await db.wallet_transactions.insert_one(commission_tx)

        await db.platform.update_one(
            {"_id": "platform"}, {"$inc": {"totalOrdersProcessed": 1}}
        )

    async def refund(self, payment_attempt: PaymentAttempt) -> PaymentAttempt:
        reference = payment_attempt.providerReference or payment_attempt.stripePaymentIntentId
        if not reference:
            raise ValueError("No hay Payment Intent de Stripe asociado")

        try:
            refund = await asyncio.to_thread(
                functools.partial(
                    stripe.Refund.create,
                    payment_intent=reference,
                )
            )

            logger.info(f"Stripe refund created: {refund.id}")

            return await payment_attempts_repo.complete_refund(
                payment_attempt.id, payment_attempt.totalAmount, refund.id
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            raise ValueError(f"Error de Stripe: {str(e)}")
