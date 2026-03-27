"""GraphQL query resolvers for Payment Methods and Payment Attempts."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, payment_methods_repo
from repositories.payments_attempt_repository import payment_attempts_repo
from schema.payments.types import (
    CashKycAccountStatusResult,
    CashKycPolicyResult,
    CashKycStatusResult,
    GlobalCashKycStatusResult,
    PaymentAttemptType,
    PaymentMethodType,
    payment_attempt_to_type,
)
from services.payments_service import payment_service
from utils.graphql_auth import apply_optional_jwt
from utils.serialization import to_strawberry_dict


def _payment_method_to_type(pm) -> PaymentMethodType:
    data = to_strawberry_dict(pm)
    data["id"] = str(pm.id)
    return PaymentMethodType(**data)


@strawberry.type
class PaymentMethodQuery:
    @strawberry.field(
        description="Obtener todos los métodos de pago disponibles. Si se provee branchId, retorna solo los aceptados por ese branch."
    )
    async def payment_methods(
        self, info: Info, branch_id: Optional[str] = None, jwt: Optional[str] = None
    ) -> List[PaymentMethodType]:
        apply_optional_jwt(jwt, info)

        if branch_id:
            branch = await branches_repo.get_by_id(branch_id)
            if not branch or not branch.paymentMethodIds:
                return []
            payment_methods = await payment_methods_repo.get_by_ids(
                branch.paymentMethodIds
            )
        else:
            payment_methods = await payment_methods_repo.get_all()

        return [_payment_method_to_type(pm) for pm in payment_methods]

    @strawberry.field(description="Obtener método de pago por ID")
    async def payment_method(
        self, info: Info, id: str, jwt: Optional[str] = None
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
            return _payment_method_to_type(payment_method)
        return None

    @strawberry.field(description="Obtener métodos de pago por moneda")
    async def payment_methods_by_currency(
        self, info: Info, currency: str, jwt: Optional[str] = None
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
        return [_payment_method_to_type(pm) for pm in payment_methods]

    @strawberry.field(description="Obtener métodos de pago por tipo")
    async def payment_methods_by_method(
        self, info: Info, method: str, jwt: Optional[str] = None
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
        return [_payment_method_to_type(pm) for pm in payment_methods]

    # ============================================
    # Payment Attempt Queries
    # ============================================

    @strawberry.field(description="Obtener intento de pago por ID")
    async def payment_attempt(
        self, info: Info, id: str, jwt: str
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
        self, info: Info, orderId: str, jwt: str
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
        self, info: Info, orderId: str, jwt: str
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

    @strawberry.field(description="Obtiene la política KYC de efectivo para una orden")
    async def cash_kyc_policy(
        self, info: Info, orderId: str, jwt: str
    ) -> CashKycPolicyResult:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        try:
            policy = await payment_service.get_cash_kyc_policy(orderId, user_id)
            return CashKycPolicyResult(**policy)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(
        description="Obtiene el estado KYC de un intento de pago en efectivo"
    )
    async def cash_kyc_status(
        self, info: Info, paymentAttemptId: str, jwt: str
    ) -> CashKycStatusResult:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        try:
            status = await payment_service.get_cash_kyc_status(
                paymentAttemptId, user_id
            )
            return CashKycStatusResult(**status)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(
        description="Obtiene estado KYC reusable por cuenta para un merchant"
    )
    async def cash_kyc_status_by_account(
        self,
        info: Info,
        merchantId: str,
        jwt: str,
        branchId: Optional[str] = None,
    ) -> CashKycAccountStatusResult:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        try:
            status = await payment_service.get_cash_kyc_status_by_account(
                merchant_id=merchantId,
                user_id=user_id,
                branch_id=branchId,
            )
            return CashKycAccountStatusResult(**status)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(
        description="Obtiene política KYC de efectivo por merchant/branch sin requerir orden"
    )
    async def cash_kyc_policy_by_merchant(
        self,
        info: Info,
        merchantId: str,
        jwt: str,
        branchId: Optional[str] = None,
    ) -> CashKycPolicyResult:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        try:
            policy = await payment_service.get_cash_kyc_policy_by_merchant(
                merchant_id=merchantId,
                user_id=user_id,
                branch_id=branchId,
            )
            return CashKycPolicyResult(**policy)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.field(
        description="Obtiene estado global KYC de la cuenta del usuario para cash"
    )
    async def global_cash_kyc_status(
        self,
        info: Info,
        jwt: str,
    ) -> GlobalCashKycStatusResult:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        try:
            status = await payment_service.get_global_cash_kyc_status(user_id=user_id)
            return GlobalCashKycStatusResult(**status)
        except ValueError as e:
            raise Exception(str(e))
