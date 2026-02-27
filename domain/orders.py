"""Pydantic models for Orders, Delivery Persons, and Location Updates."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class OrderStatus(str, Enum):
    """Order status enum."""

    PENDING_PAYMENT = "pending_payment"  # Waiting for payment
    PAYMENT_IN_PROGRESS = "payment_in_progress"  # Payment being processed
    PENDING_ACCEPTANCE = "pending_acceptance"  # Waiting for business to accept
    MODIFIED_BY_STORE = "modified_by_store"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY_FOR_PICKUP = "ready_for_pickup"
    ON_THE_WAY = "on_the_way"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    """Payment status enum."""

    PENDING = "pending"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscountType(str, Enum):
    """Discount type enum."""

    PREMIUM = "premium"
    LEVEL = "level"
    PROMO = "promo"


class OrderActor(str, Enum):
    """Actor who performed an action on the order."""

    CUSTOMER = "customer"
    BUSINESS = "business"
    SYSTEM = "system"
    DELIVERY = "delivery"


class VehicleType(str, Enum):
    """Delivery vehicle type."""

    MOTO = "moto"
    BICICLETA = "bicicleta"
    AUTO = "auto"
    A_PIE = "a_pie"


class AddressType(str, Enum):
    """Type of delivery address location."""

    HOUSE = "house"          # Casa
    APARTMENT = "apartment"  # Apartamento / Edificio
    OFFICE = "office"        # Oficina
    OTHER = "other"          # Otro


class GeoPoint(BaseModel):
    """GeoJSON Point for coordinates."""

    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class OrderComboModifier(BaseModel):
    """Modificador aplicado a un producto en un combo."""

    name: str
    priceAdjustment: float


class OrderComboSelectedOption(BaseModel):
    """Opción seleccionada por el cliente en un combo."""

    productId: PyObjectId
    name: str
    price: float
    quantity: int
    priceAdjustment: float
    modifiers: List[OrderComboModifier] = []


class OrderComboSelection(BaseModel):
    """Selección hecha por el cliente en un slot del combo."""

    slotId: str
    slotName: str
    selectedOptions: List[OrderComboSelectedOption]


class OrderItem(BaseModel):
    """Item in an order (can be a product or combo)."""

    itemId: str  # productId o comboId
    itemType: str = "product"  # "product" | "combo"
    name: str
    basePrice: float  # Precio base (para combos, suma de productos)
    finalPrice: float  # Precio final con ajustes y descuentos
    quantity: int
    imageUrl: Optional[str] = None
    wasModifiedByStore: bool = False

    # Solo para combos
    comboSelections: Optional[List[OrderComboSelection]] = None
    discountType: Optional[str] = None  # "none" | "percentage" | "fixed"
    discountValue: Optional[float] = None

    # Mantener compatibilidad con órdenes antiguas (productos simples)
    @property
    def productId(self) -> str:
        """Alias para compatibilidad."""
        return self.itemId

    @property
    def price(self) -> float:
        """Alias para compatibilidad."""
        return self.finalPrice


class OrderDiscount(BaseModel):
    """Discount applied to an order."""

    id: str
    title: str
    amount: float
    type: DiscountType


class DeliveryAddress(BaseModel):
    """Delivery address for an order."""

    street: str
    city: Optional[str] = None
    reference: Optional[str] = None
    coordinates: GeoPoint

    # Delivery instruction fields (Uber Eats / Glovo style)
    addressType: AddressType = AddressType.HOUSE
    buildingName: Optional[str] = None       # Nombre del edificio/conjunto
    floor: Optional[str] = None              # Piso (ej: "3", "PB")
    apartment: Optional[str] = None          # Número de apartamento (ej: "3B")
    deliveryInstructions: Optional[str] = None  # Instrucciones libres (ej: "Tocar timbre 2 veces")


class PickupAddress(BaseModel):
    """Pickup address (branch location) for an order."""

    street: Optional[str] = None
    coordinates: GeoPoint


class OrderTimeline(BaseModel):
    """Timeline event for order history."""

    status: OrderStatus
    timestamp: datetime
    message: str
    actor: OrderActor


class OrderComment(BaseModel):
    """Comment on an order."""

    id: str
    author: OrderActor
    message: str
    timestamp: datetime


class Order(BaseModel):
    """Order model."""

    id: PyObjectId = Field(alias="_id")
    orderNumber: str
    customerId: PyObjectId
    branchId: PyObjectId
    businessId: PyObjectId
    items: List[OrderItem]
    subtotal: float
    deliveryFee: float
    deliveryMode: str = "app"  # "app" | "branch" | "pickup_only"
    deliveryZoneId: Optional[str] = None  # H3 index de la zona (si fue por app)
    discounts: List[OrderDiscount] = []
    total: float
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PENDING_ACCEPTANCE
    deliveryAddress: DeliveryAddress
    deliveryPersonId: Optional[PyObjectId] = None
    estimatedDeliveryTime: Optional[datetime] = None
    timeline: List[OrderTimeline] = []
    comments: List[OrderComment] = []
    paymentMethod: str
    paymentStatus: PaymentStatus = PaymentStatus.PENDING
    paymentId: Optional[str] = None
    currentPaymentAttemptId: Optional[PyObjectId] = None  # Current active payment attempt
    paidAt: Optional[datetime] = None  # When payment was completed
    deliveryFeePaid: float = 0.0  # Delivery fee actually paid (for tracking)

    pickupAddress: Optional[PickupAddress] = None  # Branch address for pickup
    branchH3: Optional[str] = None  # H3 index of branch location for geo queries

    # Delivery tracking timestamps & metrics
    assignedAt: Optional[datetime] = None  # When delivery person was assigned
    pickedUpAt: Optional[datetime] = None  # When delivery person picked up the order
    completedAt: Optional[datetime] = None  # When order was delivered
    deliveryDistanceKm: Optional[float] = None  # Distance traveled in km
    deliveryDurationMin: Optional[int] = None  # Minutes from assignment to delivery
    deliveryEarnings: Optional[float] = None  # Amount earned by delivery person

    rating: Optional[int] = None
    ratingComment: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    lastStatusAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class DeliveryRequestStatus(str, Enum):
    """Status of a delivery person's request to link to a branch."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DeliveryPerson(BaseModel):
    """Delivery person model."""

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId
    name: str
    phone: Optional[str] = None
    rating: float = 5.0
    totalDeliveries: int = 0
    vehicleType: VehicleType
    vehiclePlate: Optional[str] = None
    profileImageUrl: Optional[str] = None
    isActive: bool = True
    isOnline: bool = False
    currentLocation: Optional[GeoPoint] = None
    currentOrderId: Optional[PyObjectId] = None
    linkedBranchIds: List[PyObjectId] = []
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class BranchDeliveryRequest(BaseModel):
    """Request by a delivery person to be linked to a branch."""

    id: PyObjectId = Field(alias="_id")
    deliveryPersonId: PyObjectId
    branchId: PyObjectId
    status: DeliveryRequestStatus = DeliveryRequestStatus.PENDING
    message: Optional[str] = None
    respondedBy: Optional[PyObjectId] = None
    respondedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class OrderLocationUpdate(BaseModel):
    """Location update for order tracking."""

    id: PyObjectId = Field(alias="_id")
    orderId: PyObjectId
    deliveryPersonId: PyObjectId
    location: GeoPoint
    timestamp: datetime
    speed: Optional[float] = None
    heading: Optional[float] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


# Allowed state transitions
ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    OrderStatus.PENDING_ACCEPTANCE.value: [
        OrderStatus.ACCEPTED.value,
        OrderStatus.MODIFIED_BY_STORE.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.MODIFIED_BY_STORE.value: [
        OrderStatus.ACCEPTED.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.ACCEPTED.value: [
        OrderStatus.PREPARING.value,
        OrderStatus.READY_FOR_PICKUP.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.PREPARING.value: [
        OrderStatus.READY_FOR_PICKUP.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.READY_FOR_PICKUP.value: [
        OrderStatus.ON_THE_WAY.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.ON_THE_WAY.value: [
        OrderStatus.DELIVERED.value,
        OrderStatus.CANCELLED.value,
    ],
    OrderStatus.DELIVERED.value: [],
    OrderStatus.CANCELLED.value: [],
}
