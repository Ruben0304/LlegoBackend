"""GraphQL input types for Orders."""

from enum import Enum
from typing import List, Optional

import strawberry

from .types import OrderStatusEnum


@strawberry.enum
class AddressTypeInput(Enum):
    """Type of delivery address location."""

    HOUSE = "house"
    APARTMENT = "apartment"
    OFFICE = "office"
    OTHER = "other"


@strawberry.enum
class OrderItemTypeInput(Enum):
    PRODUCT = "product"
    COMBO = "combo"
    SHOWCASE = "showcase"


@strawberry.input
class OrderComboModifierInput:
    """Selected modifier name for a combo option."""

    name: str


@strawberry.input
class OrderComboSelectedOptionInput:
    """Selected option within a combo slot."""

    productId: str
    quantity: int = 1
    modifiers: List[OrderComboModifierInput] = strawberry.field(default_factory=list)


@strawberry.input
class OrderComboSlotSelectionInput:
    """Customer selections for one combo slot."""

    slotId: str
    selectedOptions: List[OrderComboSelectedOptionInput]


@strawberry.input
class OrderItemInput:
    quantity: int
    itemType: OrderItemTypeInput = OrderItemTypeInput.PRODUCT
    productId: Optional[str] = None
    comboId: Optional[str] = None
    comboSelections: List[OrderComboSlotSelectionInput] = strawberry.field(
        default_factory=list
    )
    showcaseId: Optional[str] = None
    description: Optional[str] = None


@strawberry.input
class DeliveryAddressInput:
    street: str
    latitude: float
    longitude: float
    city: Optional[str] = None
    reference: Optional[str] = None
    # Delivery instruction fields (Uber Eats / Glovo style)
    addressType: AddressTypeInput = AddressTypeInput.HOUSE
    buildingName: Optional[str] = None      # Nombre del edificio/conjunto
    floor: Optional[str] = None             # Piso (ej: "3", "PB")
    apartment: Optional[str] = None         # Número de apartamento (ej: "3B")
    deliveryInstructions: Optional[str] = None  # Instrucciones libres (ej: "Tocar timbre 2 veces")


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


@strawberry.input
class RequestBranchLinkInput:
    branchId: str
    message: Optional[str] = None


@strawberry.input
class RespondBranchLinkInput:
    requestId: str
    accept: bool
