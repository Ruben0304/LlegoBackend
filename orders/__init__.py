"""Orders module for order management and delivery tracking."""
from .models import (
    Order,
    OrderItem,
    OrderDiscount,
    DeliveryAddress,
    OrderTimeline,
    OrderComment,
    DeliveryPerson,
    OrderLocationUpdate,
    OrderStatus,
    PaymentStatus,
    DiscountType,
    OrderActor,
    VehicleType,
)
from .repository import OrderRepository, DeliveryPersonRepository, OrderLocationRepository
from .service import OrderService

# Repository instances
orders_repo = OrderRepository()
delivery_persons_repo = DeliveryPersonRepository()
order_locations_repo = OrderLocationRepository()
order_service = OrderService()

__all__ = [
    # Models
    "Order",
    "OrderItem",
    "OrderDiscount",
    "DeliveryAddress",
    "OrderTimeline",
    "OrderComment",
    "DeliveryPerson",
    "OrderLocationUpdate",
    "OrderStatus",
    "PaymentStatus",
    "DiscountType",
    "OrderActor",
    "VehicleType",
    # Repositories
    "OrderRepository",
    "DeliveryPersonRepository",
    "OrderLocationRepository",
    "orders_repo",
    "delivery_persons_repo",
    "order_locations_repo",
    # Service
    "OrderService",
    "order_service",
]
