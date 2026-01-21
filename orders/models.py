"""Pydantic models for Orders, Delivery Persons, and Location Updates."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


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


class GeoPoint(BaseModel):
    """GeoJSON Point for coordinates."""
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]


class OrderItem(BaseModel):
    """Item in an order (snapshot at order creation time)."""
    productId: str
    name: str
    price: float
    quantity: int
    imageUrl: str
    wasModifiedByStore: bool = False


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
    id: str = Field(alias="_id")
    orderNumber: str
    customerId: str
    branchId: str
    businessId: str
    items: List[OrderItem]
    subtotal: float
    deliveryFee: float
    discounts: List[OrderDiscount] = []
    total: float
    currency: str = "USD"
    status: OrderStatus = OrderStatus.PENDING_ACCEPTANCE
    deliveryAddress: DeliveryAddress
    deliveryPersonId: Optional[str] = None
    estimatedDeliveryTime: Optional[datetime] = None
    timeline: List[OrderTimeline] = []
    comments: List[OrderComment] = []
    paymentMethod: str
    paymentStatus: PaymentStatus = PaymentStatus.PENDING
    paymentId: Optional[str] = None
    currentPaymentAttemptId: Optional[str] = None  # Current active payment attempt
    paidAt: Optional[datetime] = None  # When payment was completed
    deliveryFeePaid: float = 0.0  # Delivery fee actually paid (for tracking)
    rating: Optional[int] = None
    ratingComment: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    lastStatusAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class DeliveryPerson(BaseModel):
    """Delivery person model."""
    id: str = Field(alias="_id")
    userId: str
    name: str
    phone: str
    rating: float = 5.0
    totalDeliveries: int = 0
    vehicleType: VehicleType
    vehiclePlate: Optional[str] = None
    profileImageUrl: Optional[str] = None
    isActive: bool = True
    isOnline: bool = False
    currentLocation: Optional[GeoPoint] = None
    currentOrderId: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class OrderLocationUpdate(BaseModel):
    """Location update for order tracking."""
    id: str = Field(alias="_id")
    orderId: str
    deliveryPersonId: str
    location: GeoPoint
    timestamp: datetime
    speed: Optional[float] = None
    heading: Optional[float] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


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
