"""GraphQL query resolvers for Payment Methods and Payment Attempts."""

from datetime import datetime
from typing import List, Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from clients.mongodb_client import get_database
from repositories import branches_repo, payment_methods_repo, payments_repo
from repositories.payments_attempt_repository import payment_attempts_repo
from schema.payments.types import (
    CashKycAccountStatusResult,
    CashKycPolicyResult,
    CashKycStatusResult,
    GlobalCashKycStatusResult,
    OcrPaymentsConnectionType,
    PaymentAttemptType,
    PaymentAttemptAdminConnectionType,
    PaymentAttemptAdminRowType,
    PaymentMethodType,
    PaymentType,
    payment_attempt_to_type,
)
from services.payments_service import payment_service
from utils.graphql_auth import apply_optional_jwt, require_role
from utils.serialization import to_strawberry_dict


def _payment_method_to_type(pm) -> PaymentMethodType:
    data = to_strawberry_dict(pm)
    data["id"] = str(pm.id)
    return PaymentMethodType(**data)


def _to_object_id(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return value


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

    @strawberry.field(
        description="(Admin) Listar intentos de pago con método y metadata del pedido"
    )
    async def admin_payment_attempts(
        self,
        info: Info,
        jwt: str,
        statusIn: Optional[List[str]] = None,
        paymentMethodId: Optional[str] = None,
        branchId: Optional[str] = None,
        businessId: Optional[str] = None,
        customerId: Optional[str] = None,
        orderNumber: Optional[str] = None,
        fromDate: Optional[datetime] = None,
        toDate: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaymentAttemptAdminConnectionType:
        require_role(jwt, info, ["admin", "manager"])

        db = get_database()
        orders_collection = db["orders"]

        order_ids = None
        if branchId or businessId or customerId or orderNumber:
            orders_query = {}
            if branchId:
                orders_query["branchId"] = _to_object_id(branchId)
            if businessId:
                orders_query["businessId"] = _to_object_id(businessId)
            if customerId:
                orders_query["customerId"] = _to_object_id(customerId)
            if orderNumber:
                orders_query["orderNumber"] = orderNumber

            order_ids = await orders_collection.distinct("_id", orders_query)

        attempts, total = await payment_attempts_repo.list_filtered(
            order_ids=order_ids,
            payment_method_id=paymentMethodId,
            status_in=statusIn,
            from_date=fromDate,
            to_date=toDate,
            limit=limit,
            offset=offset,
        )

        # Fetch order metadata in one query
        order_meta_by_id = {}
        if attempts:
            raw_ids = []
            for a in attempts:
                try:
                    raw_ids.append(a.orderId)
                except Exception:
                    continue
            # orderId in attempts is already stored as string in domain model,
            # but in Mongo it is ObjectId. Try both forms.
            mongo_ids = []
            for oid in raw_ids:
                try:
                    mongo_ids.append(ObjectId(str(oid)))
                except Exception:
                    mongo_ids.append(oid)
            cursor = orders_collection.find(
                {"_id": {"$in": mongo_ids}},
                {
                    "_id": 1,
                    "orderNumber": 1,
                    "branchId": 1,
                    "businessId": 1,
                    "customerId": 1,
                },
            )
            async for doc in cursor:
                order_meta_by_id[str(doc["_id"])] = doc

        # Fetch payment methods in bulk
        pm_by_id = {}
        pm_ids = list({str(a.paymentMethodId) for a in attempts})
        if pm_ids:
            pms = await payment_methods_repo.get_by_ids(pm_ids)
            pm_by_id = {str(pm.id): _payment_method_to_type(pm) for pm in pms}

        rows: List[PaymentAttemptAdminRowType] = []
        for a in attempts:
            attempt_type = payment_attempt_to_type(a)
            meta = order_meta_by_id.get(str(a.orderId)) or {}
            rows.append(
                PaymentAttemptAdminRowType(
                    attempt=attempt_type,
                    paymentMethod=pm_by_id.get(str(a.paymentMethodId)),
                    orderNumber=meta.get("orderNumber"),
                    branchId=str(meta.get("branchId")) if meta.get("branchId") is not None else None,
                    businessId=str(meta.get("businessId")) if meta.get("businessId") is not None else None,
                    customerId=str(meta.get("customerId")) if meta.get("customerId") is not None else None,
                )
            )

        return PaymentAttemptAdminConnectionType(
            rows=rows,
            totalCount=total,
            hasMore=(offset + len(rows)) < total,
        )

    @strawberry.field(
        description="(Admin) Listar pagos OCR (colección `pagos`) con filtros y paginación"
    )
    async def admin_ocr_payments(
        self,
        info: Info,
        jwt: str,
        banco: Optional[str] = None,
        numeroTransferencia: Optional[str] = None,
        fromDate: Optional[datetime] = None,
        toDate: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> OcrPaymentsConnectionType:
        require_role(jwt, info, ["admin", "manager"])

        payments, total = await payments_repo.list_filtered(
            banco=banco,
            numero_transferencia=numeroTransferencia,
            from_date=fromDate,
            to_date=toDate,
            limit=limit,
            offset=offset,
        )
        return OcrPaymentsConnectionType(
            payments=[PaymentType(**to_strawberry_dict(p)) for p in payments],
            totalCount=total,
            hasMore=(offset + len(payments)) < total,
        )

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
        customerId: Optional[str] = None,
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
                customer_id=customerId,
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
