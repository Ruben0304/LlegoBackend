"""GraphQL query resolvers for Payment Methods and Payment Attempts."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from schema.payments.types import PaymentAttemptType, PaymentMethodType, payment_attempt_to_type
from repositories import payment_methods_repo
from repositories.payments_attempt_repository import payment_attempts_repo
from services.payments_service import payment_service
from utils.graphql_auth import apply_optional_jwt

@strawberry.type
class PaymentMethodQuery:
    @strawberry.field(description="Obtener todos los métodos de pago disponibles")
    async def payment_methods(
        self,
        info: Info,
        jwt: Optional[str] = None
    ) -> List[PaymentMethodType]:
        """
        Get all available payment methods.

        Returns:
            List of all payment methods in the system
        """
        apply_optional_jwt(jwt, info)

        payment_methods = await payment_methods_repo.get_all()
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]

    @strawberry.field(description="Obtener método de pago por ID")
    async def payment_method(
        self,
        info: Info,
        id: str,
        jwt: Optional[str] = None
    ) -> Optional[PaymentMethodType]:
        """
        Get a payment method by ID.

        Args:
            id: Payment method ID

        Returns:
            Payment method or None if not found
        """
        apply_optional_jwt(jwt, info)

        payment_method = await payment_methods_repo.get_by_id(id)
        if payment_method:
            return PaymentMethodType(**payment_method.model_dump())
        return None

    @strawberry.field(description="Obtener métodos de pago por moneda")
    async def payment_methods_by_currency(
        self,
        info: Info,
        currency: str,
        jwt: Optional[str] = None
    ) -> List[PaymentMethodType]:
        """
        Get payment methods filtered by currency.

        Args:
            currency: Currency code (e.g., "CUP", "USD")

        Returns:
            List of payment methods for the specified currency
        """
        apply_optional_jwt(jwt, info)

        payment_methods = await payment_methods_repo.get_by_currency(currency)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]

    @strawberry.field(description="Obtener métodos de pago por tipo")
    async def payment_methods_by_method(
        self,
        info: Info,
        method: str,
        jwt: Optional[str] = None
    ) -> List[PaymentMethodType]:
        """
        Get payment methods filtered by method type.

        Args:
            method: Method type (e.g., "tarjeta", "efectivo", "transferencia")

        Returns:
            List of payment methods for the specified method type
        """
        apply_optional_jwt(jwt, info)

        payment_methods = await payment_methods_repo.get_by_method(method)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]

    # ============================================
    # Payment Attempt Queries
    # ============================================

    @strawberry.field(description="Obtener intento de pago por ID")
    async def payment_attempt(
        self,
        info: Info,
        id: str,
        jwt: str
    ) -> Optional[PaymentAttemptType]:
        """
        Get a payment attempt by ID.

        Requires authentication and authorization (must be customer, business, or delivery).

        Args:
            id: Payment attempt ID
            jwt: User JWT token

        Returns:
            Payment attempt or None if not found/unauthorized
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.get_payment_attempt(id, user_id)
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(description="Obtener intentos de pago de un pedido")
    async def payment_attempts_by_order(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> List[PaymentAttemptType]:
        """
        Get all payment attempts for an order.

        Args:
            orderId: Order ID
            jwt: User JWT token

        Returns:
            List of payment attempts for the order
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        attempts = await payment_attempts_repo.get_by_order_id(orderId)
        return [payment_attempt_to_type(a) for a in attempts]

    @strawberry.field(description="Obtener el intento de pago activo de un pedido")
    async def active_payment_attempt(
        self,
        info: Info,
        orderId: str,
        jwt: str
    ) -> Optional[PaymentAttemptType]:
        """
        Get the active (non-final) payment attempt for an order.

        Args:
            orderId: Order ID
            jwt: User JWT token

        Returns:
            Active payment attempt or None
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        attempt = await payment_attempts_repo.get_active_by_order_id(orderId)
        return payment_attempt_to_type(attempt) if attempt else None
