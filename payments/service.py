"""Payment service for handling payment processing logic."""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import uuid4
from bson import ObjectId
import stripe
import logging

from core.config import settings
from clients.mongodb_client import get_database
from .models import PaymentAttempt, PaymentAttemptStatus
from .repository import PaymentAttemptRepository
from repositories import branches_repo, users_repo, businesses_repo

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key


class PaymentService:
    """Service for payment processing business logic."""

    def __init__(self):
        self.payment_attempts_repo = PaymentAttemptRepository()

    async def _get_order(self, order_id: str):
        """Get order by ID."""
        db = get_database()
        try:
            doc = await db.orders.find_one({"_id": ObjectId(order_id)})
        except Exception:
            doc = await db.orders.find_one({"_id": order_id})
        return doc

    async def _get_payment_method(self, payment_method_id: str):
        """Get payment method by ID."""
        db = get_database()
        try:
            doc = await db.payment_methods.find_one({"_id": ObjectId(payment_method_id)})
        except Exception:
            doc = await db.payment_methods.find_one({"_id": payment_method_id})
        return doc

    async def _get_branch(self, branch_id: str):
        """Get branch by ID using the branch repository."""
        branch = await branches_repo.get_by_id(branch_id)
        return branch.model_dump() if branch else None

    async def _get_user(self, user_id: str):
        """Get user by ID using the user repository."""
        user = await users_repo.get_by_id(user_id)
        return user.model_dump() if user else None

    async def _get_platform(self):
        """Get or create platform document."""
        db = get_database()
        doc = await db.platform.find_one({"_id": "platform"})
        if not doc:
            doc = {
                "_id": "platform",
                "name": "Llego",
                "wallet": {"local": 0.0, "usd": 0.0},
                "walletStatus": "active",
                "totalCommissionsCollected": 0.0,
                "totalOrdersProcessed": 0,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            await db.platform.insert_one(doc)
        return doc

    def _calculate_amounts(
        self,
        order: dict,
        payment_method: dict,
        include_delivery: bool = True
    ) -> Tuple[float, float, float, float, str]:
        """
        Calculate payment amounts.

        Returns:
            Tuple of (subtotal, delivery_fee, commission, total, currency)
        """
        subtotal = float(order.get("subtotal", 0))
        delivery_fee = float(order.get("deliveryFee", 0)) if include_delivery else 0.0

        # Determine currency based on payment method
        pm_currency = payment_method.get("currency", "USD").upper()
        currency = "usd" if pm_currency == "USD" else "local"

        # Calculate commission
        commission_percent = float(payment_method.get("commissionPercent", 0))

        # For cash payments with delivery, add delivery fee percentage
        if payment_method.get("method") == "cash" and include_delivery:
            delivery_fee_percent = float(payment_method.get("deliveryFeePercent", 0))
            # Apply delivery fee percentage to delivery fee
            delivery_fee = delivery_fee * (1 + delivery_fee_percent / 100)

        # Calculate base for commission (subtotal + delivery if applicable)
        base_amount = subtotal + delivery_fee
        commission = round(base_amount * (commission_percent / 100), 2)

        total = round(subtotal + delivery_fee + commission, 2)

        return subtotal, delivery_fee, commission, total, currency

    async def initiate_payment(
        self,
        order_id: str,
        payment_method_id: str,
        user_id: str,
        include_delivery_fee: bool = True
    ) -> PaymentAttempt:
        """
        Initiate a payment for an order.

        This creates a PaymentAttempt and handles the initial processing
        based on the payment method type.

        Args:
            order_id: The order to pay for
            payment_method_id: The payment method to use
            user_id: The user initiating the payment
            include_delivery_fee: Whether to include delivery in this payment

        Returns:
            PaymentAttempt with appropriate status and fields
        """
        # Get order
        order = await self._get_order(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify user owns the order
        if order.get("customerId") != user_id:
            raise ValueError("No autorizado para pagar este pedido")

        # Check order status - must be in a payable state
        # Solo permitir pago después de que negocio acepte
        payable_statuses = ["accepted", "modified_by_store"]
        if order.get("status") not in payable_statuses:
            raise ValueError(f"El pedido no está en un estado que permita pago: {order.get('status')}")

        # Check if there's already an active payment attempt
        existing = await self.payment_attempts_repo.get_active_by_order_id(order_id)
        if existing:
            raise ValueError("Ya existe un intento de pago activo para este pedido")

        # Get payment method
        payment_method = await self._get_payment_method(payment_method_id)
        if not payment_method:
            raise ValueError("Método de pago no encontrado")

        if not payment_method.get("isActive", True):
            raise ValueError("Método de pago no disponible")

        # Calculate amounts
        subtotal, delivery_fee, commission, total, currency = self._calculate_amounts(
            order, payment_method, include_delivery_fee
        )

        # Create payment attempt
        attempt_id = str(ObjectId())
        expires_at = None
        if payment_method.get("expirationMinutes"):
            expires_at = datetime.utcnow() + timedelta(
                minutes=payment_method["expirationMinutes"]
            )

        payment_attempt = PaymentAttempt(
            _id=attempt_id,
            orderId=order_id,
            paymentMethodId=payment_method_id,
            subtotal=subtotal,
            deliveryFee=delivery_fee,
            includesDeliveryFee=include_delivery_fee,
            taxAmount=0.0,  # Future
            discountAmount=0.0,  # Future
            commissionAmount=commission,
            totalAmount=total,
            currency=currency,
            status=PaymentAttemptStatus.PENDING,
            expiresAt=expires_at,
        )

        # Handle based on payment method type
        method_type = payment_method.get("method", "").lower()

        if method_type == "wallet":
            # Process wallet payment immediately
            payment_attempt = await self._process_wallet_payment(
                payment_attempt, order, payment_method, user_id
            )

        elif method_type == "stripe":
            # Create Stripe Payment Intent
            payment_attempt = await self._create_stripe_payment_intent(
                payment_attempt, order, payment_method, user_id
            )

        elif method_type == "transfer":
            # Manual transfer - wait for proof
            payment_attempt.status = PaymentAttemptStatus.AWAITING_PROOF

        elif method_type == "cash":
            # Cash on delivery - wait for delivery confirmation
            payment_attempt.status = PaymentAttemptStatus.AWAITING_DELIVERY

        else:
            raise ValueError(f"Método de pago no soportado: {method_type}")

        # Save payment attempt
        await self.payment_attempts_repo.create(payment_attempt)

        # Update order with current payment attempt
        await self._update_order_payment_attempt(order_id, attempt_id)

        return payment_attempt

    async def _process_wallet_payment(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str
    ) -> PaymentAttempt:
        """Process an immediate wallet payment."""
        db = get_database()

        # Get user and verify balance
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")

        user_wallet = user.get("wallet", {"local": 0, "usd": 0})
        currency = payment_attempt.currency
        user_balance = float(user_wallet.get(currency, 0))

        if user_balance < payment_attempt.totalAmount:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = "Saldo insuficiente"
            return payment_attempt

        # Get branch
        branch = await self._get_branch(order.get("branchId"))
        if not branch:
            raise ValueError("Sucursal no encontrada")

        # Get platform
        platform = await self._get_platform()

        # Calculate amounts
        amount_to_business = payment_attempt.subtotal + payment_attempt.deliveryFee
        commission = payment_attempt.commissionAmount

        # Atomic debit from user wallet
        try:
            user_id_obj = ObjectId(user_id)
        except Exception:
            user_id_obj = user_id

        result = await db.users.update_one(
            {
                "_id": user_id_obj,
                f"wallet.{currency}": {"$gte": payment_attempt.totalAmount}
            },
            {"$inc": {f"wallet.{currency}": -payment_attempt.totalAmount}}
        )

        if result.modified_count == 0:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = "Saldo insuficiente o modificación concurrente"
            return payment_attempt

        # Credit branch wallet
        branch_id = order.get("branchId")
        await db.branches.update_one(
            {"_id": branch_id},
            {"$inc": {f"wallet.{currency}": amount_to_business}}
        )

        # Credit platform wallet (commission)
        if commission > 0:
            await db.platform.update_one(
                {"_id": "platform"},
                {
                    "$inc": {
                        f"wallet.{currency}": commission,
                        "totalCommissionsCollected": commission if currency == "usd" else 0,
                    }
                }
            )

        # Create transaction records
        now = datetime.utcnow()

        # User debit transaction
        user_tx_id = str(uuid4())
        user_tx = {
            "_id": user_tx_id,
            "fromOwnerId": user_id,
            "fromOwnerType": "user",
            "toOwnerId": order.get("branchId"),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "order_payment",
            "status": "completed",
            "description": f"Pago pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": payment_attempt.id,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(user_tx)

        # Business credit transaction
        business_tx_id = str(uuid4())
        business_tx = {
            "_id": business_tx_id,
            "fromOwnerId": user_id,
            "fromOwnerType": "user",
            "toOwnerId": order.get("branchId"),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "order_received",
            "status": "completed",
            "description": f"Recibido pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": payment_attempt.id,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        # Commission transaction
        commission_tx_id = str(uuid4())
        if commission > 0:
            commission_tx = {
                "_id": commission_tx_id,
                "fromOwnerId": user_id,
                "fromOwnerType": "user",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission",
                "status": "completed",
                "description": f"Comisión pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": payment_attempt.id,
                },
                "createdAt": now,
                "completedAt": now,
            }
            await db.wallet_transactions.insert_one(commission_tx)

        # Update platform stats
        await db.platform.update_one(
            {"_id": "platform"},
            {"$inc": {"totalOrdersProcessed": 1}}
        )

        # Update payment attempt
        payment_attempt.status = PaymentAttemptStatus.COMPLETED
        payment_attempt.completedAt = now
        payment_attempt.walletTransactionId = user_tx_id
        payment_attempt.businessWalletTransactionId = business_tx_id
        payment_attempt.commissionTransactionId = commission_tx_id if commission > 0 else None

        # Update order payment status
        await self._complete_order_payment(str(order.get("_id")), payment_attempt.id)

        return payment_attempt

    async def _create_stripe_payment_intent(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str
    ) -> PaymentAttempt:
        """Create a Stripe Payment Intent."""
        try:
            # Convert to cents
            amount_cents = int(payment_attempt.totalAmount * 100)

            # Create Payment Intent
            intent = stripe.PaymentIntent.create(
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

            payment_attempt.stripePaymentIntentId = intent.id
            payment_attempt.stripeClientSecret = intent.client_secret
            payment_attempt.status = PaymentAttemptStatus.PROCESSING

            logger.info(f"Created Stripe Payment Intent: {intent.id} for order {order.get('_id')}")

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = f"Error de Stripe: {str(e)}"

        return payment_attempt

    async def confirm_payment_sent(
        self,
        payment_attempt_id: str,
        user_id: str,
        proof_url: str
    ) -> PaymentAttempt:
        """
        Customer confirms they sent the payment (for manual methods).

        Args:
            payment_attempt_id: The payment attempt ID
            user_id: The user confirming
            proof_url: URL to proof/receipt image
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        # Verify ownership
        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.AWAITING_PROOF:
            raise ValueError(f"Estado no válido para confirmar: {attempt.status}")

        # Update attempt
        updated = await self.payment_attempts_repo.set_proof(
            payment_attempt_id,
            proof_url
        )

        # TODO: Notify business

        return updated

    async def confirm_payment_received(
        self,
        payment_attempt_id: str,
        user_id: str
    ) -> PaymentAttempt:
        """
        Business confirms they received the payment.

        Args:
            payment_attempt_id: The payment attempt ID
            user_id: The business user confirming
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify business ownership
        branch = await self._get_branch(order.get("branchId"))
        if not branch:
            raise ValueError("Sucursal no encontrada")

        # Check if user is manager or owner
        business = await businesses_repo.get_by_id(branch.get("businessId"))

        is_authorized = (
            business and business.ownerId == user_id
        ) or user_id in branch.get("managerIds", [])

        if not is_authorized:
            raise ValueError("No autorizado para confirmar este pago")

        if attempt.status != PaymentAttemptStatus.AWAITING_BUSINESS:
            raise ValueError(f"Estado no válido para confirmar: {attempt.status}")

        # Confirm payment
        updated = await self.payment_attempts_repo.confirm_business_received(
            payment_attempt_id
        )

        # Complete order payment
        await self._complete_order_payment(attempt.orderId, payment_attempt_id)

        # TODO: Notify customer

        return updated

    async def confirm_cash_received(
        self,
        payment_attempt_id: str,
        delivery_person_id: str
    ) -> PaymentAttempt:
        """
        Delivery person confirms they received cash payment.

        Args:
            payment_attempt_id: The payment attempt ID
            delivery_person_id: The delivery person confirming
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        if attempt.status != PaymentAttemptStatus.AWAITING_DELIVERY:
            raise ValueError(f"Estado no válido para confirmar efectivo: {attempt.status}")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify delivery person is assigned to this order
        if order.get("deliveryPersonId") != delivery_person_id:
            raise ValueError("No autorizado para confirmar este pago")

        # Confirm cash received
        updated = await self.payment_attempts_repo.confirm_delivery_cash(
            payment_attempt_id,
            delivery_person_id
        )

        # For cash payments, we need to credit the business wallet
        # The cash is physically with the delivery person, but we record it
        await self._process_cash_payment_completion(attempt, order)

        # Complete order payment
        await self._complete_order_payment(attempt.orderId, payment_attempt_id)

        return updated

    async def _process_cash_payment_completion(
        self,
        attempt: PaymentAttempt,
        order: dict
    ):
        """Process the wallet transactions for a completed cash payment."""
        db = get_database()
        now = datetime.utcnow()

        # For cash payments, we record the transaction but money flows physically
        # Create transaction records for tracking

        amount_to_business = attempt.subtotal + attempt.deliveryFee
        commission = attempt.commissionAmount
        currency = attempt.currency

        # Record business received (they'll get cash from delivery person)
        business_tx = {
            "_id": str(uuid4()),
            "fromOwnerId": order.get("customerId"),
            "fromOwnerType": "user",
            "toOwnerId": order.get("branchId"),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "cash_payment",
            "status": "completed",
            "description": f"Pago efectivo pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "paymentMethod": "cash",
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        # Commission is owed to platform (to be settled later)
        if commission > 0:
            commission_tx = {
                "_id": str(uuid4()),
                "fromOwnerId": order.get("branchId"),
                "fromOwnerType": "branch",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission_owed",
                "status": "pending",  # Will be settled when business pays platform
                "description": f"Comisión pendiente pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": attempt.id,
                },
                "createdAt": now,
                "completedAt": None,
            }
            await db.wallet_transactions.insert_one(commission_tx)

    async def dispute_payment(
        self,
        payment_attempt_id: str,
        user_id: str,
        reason: str
    ) -> PaymentAttempt:
        """
        Business disputes that they didn't receive the payment.
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify business ownership
        branch = await self._get_branch(order.get("branchId"))
        business = await businesses_repo.get_by_id(branch.get("businessId"))

        is_authorized = (
            business and business.ownerId == user_id
        ) or user_id in branch.get("managerIds", [])

        if not is_authorized:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.AWAITING_BUSINESS:
            raise ValueError(f"Estado no válido para disputar: {attempt.status}")

        return await self.payment_attempts_repo.dispute(payment_attempt_id, reason)

    async def request_refund(
        self,
        payment_attempt_id: str,
        user_id: str,
        reason: str
    ) -> PaymentAttempt:
        """
        Customer requests a refund.
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.COMPLETED:
            raise ValueError("Solo se pueden reembolsar pagos completados")

        # Check if payment method is refundable
        payment_method = await self._get_payment_method(attempt.paymentMethodId)
        if not payment_method or not payment_method.get("isRefundable", True):
            raise ValueError("Este método de pago no permite reembolsos")

        # Check order status - can't refund if already delivered
        non_refundable_statuses = ["delivered", "on_the_way"]
        if order.get("status") in non_refundable_statuses:
            raise ValueError("No se puede reembolsar un pedido ya entregado o en camino")

        return await self.payment_attempts_repo.request_refund(payment_attempt_id, reason)

    async def process_refund(
        self,
        payment_attempt_id: str,
        admin_user_id: str
    ) -> PaymentAttempt:
        """
        Process an approved refund (admin action).
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        if attempt.status != PaymentAttemptStatus.REFUND_REQUESTED:
            raise ValueError("El pago no tiene solicitud de reembolso pendiente")

        # Get payment method to determine refund process
        payment_method = await self._get_payment_method(attempt.paymentMethodId)
        method_type = payment_method.get("method", "").lower() if payment_method else ""

        if method_type == "wallet":
            return await self._process_wallet_refund(attempt)
        elif method_type == "stripe":
            return await self._process_stripe_refund(attempt)
        else:
            # Manual refunds for other methods
            return await self.payment_attempts_repo.update_status(
                payment_attempt_id,
                PaymentAttemptStatus.REFUND_PROCESSING,
            )

    async def _process_wallet_refund(self, attempt: PaymentAttempt) -> PaymentAttempt:
        """Process a wallet refund."""
        db = get_database()
        order = await self._get_order(attempt.orderId)
        now = datetime.utcnow()

        currency = attempt.currency
        refund_amount = attempt.subtotal + attempt.deliveryFee  # Refund without commission

        # Debit from business wallet
        try:
            branch_id = ObjectId(order.get("branchId"))
        except Exception:
            branch_id = order.get("branchId")

        result = await db.branches.update_one(
            {
                "_id": branch_id,
                f"wallet.{currency}": {"$gte": refund_amount}
            },
            {"$inc": {f"wallet.{currency}": -refund_amount}}
        )

        if result.modified_count == 0:
            raise ValueError("El negocio no tiene saldo suficiente para el reembolso")

        # Credit user wallet
        try:
            user_id = ObjectId(order.get("customerId"))
        except Exception:
            user_id = order.get("customerId")

        await db.users.update_one(
            {"_id": user_id},
            {"$inc": {f"wallet.{currency}": refund_amount}}
        )

        # Create refund transaction
        refund_tx_id = str(uuid4())
        refund_tx = {
            "_id": refund_tx_id,
            "fromOwnerId": order.get("branchId"),
            "fromOwnerType": "branch",
            "toOwnerId": order.get("customerId"),
            "toOwnerType": "user",
            "amount": refund_amount,
            "currency": currency,
            "type": "refund",
            "status": "completed",
            "description": f"Reembolso pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "originalAmount": attempt.totalAmount,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(refund_tx)

        # Update payment attempt
        return await self.payment_attempts_repo.complete_refund(
            attempt.id,
            refund_amount,
            refund_tx_id
        )

    async def _process_stripe_refund(self, attempt: PaymentAttempt) -> PaymentAttempt:
        """Process a Stripe refund."""
        if not attempt.stripePaymentIntentId:
            raise ValueError("No hay Payment Intent de Stripe asociado")

        try:
            # Create Stripe refund
            refund = stripe.Refund.create(
                payment_intent=attempt.stripePaymentIntentId,
                # Refund full amount minus commission (or full amount if you want)
                # For now, refund full amount
            )

            logger.info(f"Stripe refund created: {refund.id}")

            return await self.payment_attempts_repo.complete_refund(
                attempt.id,
                attempt.totalAmount,
                refund.id
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            raise ValueError(f"Error de Stripe: {str(e)}")

    async def handle_stripe_webhook(
        self,
        payment_intent_id: str,
        event_type: str
    ) -> Optional[PaymentAttempt]:
        """
        Handle Stripe webhook for order payments.

        Args:
            payment_intent_id: Stripe Payment Intent ID
            event_type: Stripe event type
        """
        attempt = await self.payment_attempts_repo.get_by_stripe_payment_intent(
            payment_intent_id
        )

        if not attempt:
            logger.warning(f"No payment attempt found for PI: {payment_intent_id}")
            return None

        if event_type == "payment_intent.succeeded":
            # Payment successful
            updated = await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.COMPLETED,
            )

            # Process the payment completion (credit business, etc.)
            order = await self._get_order(attempt.orderId)
            if order:
                await self._process_stripe_payment_completion(attempt, order)
                await self._complete_order_payment(attempt.orderId, attempt.id)

            return updated

        elif event_type == "payment_intent.payment_failed":
            # Payment failed
            return await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.FAILED,
                failedReason="Pago rechazado por Stripe",
            )

        return attempt

    async def _process_stripe_payment_completion(
        self,
        attempt: PaymentAttempt,
        order: dict
    ):
        """Process wallet credits after successful Stripe payment."""
        db = get_database()
        now = datetime.utcnow()

        amount_to_business = attempt.subtotal + attempt.deliveryFee
        commission = attempt.commissionAmount
        currency = attempt.currency

        # Credit business wallet
        branch_id = order.get("branchId")
        await db.branches.update_one(
            {"_id": branch_id},
            {"$inc": {f"wallet.{currency}": amount_to_business}}
        )

        # Credit platform commission
        if commission > 0:
            await db.platform.update_one(
                {"_id": "platform"},
                {
                    "$inc": {
                        f"wallet.{currency}": commission,
                        "totalCommissionsCollected": commission if currency == "usd" else 0,
                    }
                }
            )

        # Create transaction records
        business_tx = {
            "_id": str(uuid4()),
            "fromOwnerId": "stripe",
            "fromOwnerType": "external",
            "toOwnerId": order.get("branchId"),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "stripe_payment",
            "status": "completed",
            "description": f"Pago Stripe pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "stripePaymentIntentId": attempt.stripePaymentIntentId,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        if commission > 0:
            commission_tx = {
                "_id": str(uuid4()),
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

        # Update platform stats
        await db.platform.update_one(
            {"_id": "platform"},
            {"$inc": {"totalOrdersProcessed": 1}}
        )

    async def _update_order_payment_attempt(self, order_id: str, attempt_id: str):
        """Update order with current payment attempt ID."""
        db = get_database()
        try:
            order_id_obj = ObjectId(order_id)
        except Exception:
            order_id_obj = order_id

        await db.orders.update_one(
            {"_id": order_id_obj},
            {
                "$set": {
                    "currentPaymentAttemptId": attempt_id,
                    "updatedAt": datetime.utcnow(),
                }
            }
        )

    async def _complete_order_payment(self, order_id: str, attempt_id: str):
        """Mark order payment as completed."""
        db = get_database()
        try:
            order_id_obj = ObjectId(order_id)
        except Exception:
            order_id_obj = order_id

        await db.orders.update_one(
            {"_id": order_id_obj},
            {
                "$set": {
                    "paymentStatus": "completed",
                    "paymentId": attempt_id,
                    "paidAt": datetime.utcnow(),
                    "status": "pending_acceptance",  # Move to next status
                    "updatedAt": datetime.utcnow(),
                }
            }
        )

    async def cancel_payment(
        self,
        payment_attempt_id: str,
        user_id: str
    ) -> PaymentAttempt:
        """Cancel a pending payment attempt."""
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        # Can only cancel pending/awaiting payments
        cancellable_statuses = [
            PaymentAttemptStatus.PENDING,
            PaymentAttemptStatus.AWAITING_PROOF,
            PaymentAttemptStatus.PROCESSING,
        ]
        if attempt.status not in cancellable_statuses:
            raise ValueError(f"No se puede cancelar un pago en estado: {attempt.status}")

        # If Stripe, cancel the Payment Intent
        if attempt.stripePaymentIntentId:
            try:
                stripe.PaymentIntent.cancel(attempt.stripePaymentIntentId)
            except stripe.error.StripeError as e:
                logger.warning(f"Could not cancel Stripe PI: {e}")

        return await self.payment_attempts_repo.update_status(
            payment_attempt_id,
            PaymentAttemptStatus.CANCELLED,
        )

    async def get_payment_attempt(
        self,
        payment_attempt_id: str,
        user_id: str
    ) -> PaymentAttempt:
        """Get a payment attempt with authorization check."""
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Check authorization - customer, business manager, or delivery person
        is_customer = order.get("customerId") == user_id
        is_delivery = order.get("deliveryPersonId") == user_id

        branch = await self._get_branch(order.get("branchId"))
        is_business = user_id in branch.get("managerIds", []) if branch else False

        if not (is_customer or is_business or is_delivery):
            raise ValueError("No autorizado")

        return attempt

    async def expire_payments(self) -> int:
        """
        Expire all payment attempts that have passed their expiration time.
        This should be called by a background job.

        Returns:
            Number of expired payments
        """
        expired = await self.payment_attempts_repo.get_expired()
        count = 0

        for attempt in expired:
            await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.EXPIRED,
            )
            count += 1

            # Optionally notify user
            logger.info(f"Expired payment attempt: {attempt.id}")

        return count
