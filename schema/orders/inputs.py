"""GraphQL input types for Orders."""
import strawberry
from typing import Optional, List

from .types import OrderStatusEnum


@strawberry.input
class OrderItemInput:
    productId: str
    quantity: int


@strawberry.input
class DeliveryAddressInput:
    street: str
    latitude: float
    longitude: float
    city: Optional[str] = None
    reference: Optional[str] = None


@strawberry.input
class CreateOrderInput:
    branchId: str
    items: List[OrderItemInput]
    deliveryAddress: DeliveryAddressInput
    paymentMethod: str  # "card" | "transfer" | "cash" | "apple_pay"
    paymentIntentId: Optional[str] = None
    comments: Optional[str] = None
    promoCode: Optional[str] = None


@strawberry.input
class UpdateOrderStatusInput:
    orderId: str
    status: OrderStatusEnum
    message: Optional[str] = None


@strawberry.input
class AddOrderCommentInput:
    orderId: str
    message: str


@strawberry.input
class ModifyOrderItemsInput:
    orderId: str
    items: List[OrderItemInput]
    reason: str


@strawberry.input
class UpdateDeliveryLocationInput:
    orderId: str
    latitude: float
    longitude: float
    speed: Optional[float] = None
    heading: Optional[float] = None


@strawberry.input
class AssignDeliveryPersonInput:
    orderId: str
    deliveryPersonId: str
    estimatedMinutes: Optional[int] = None
