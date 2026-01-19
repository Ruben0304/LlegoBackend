"""GraphQL query resolvers for Payment Methods."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from schema.ai_assistant.types import PaymentMethodType
from models import payment_methods_repo
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
