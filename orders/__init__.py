"""Orders module for order management and delivery tracking."""

from .models import (
    BranchDeliveryRequest,
    DeliveryAddress,
    DeliveryPerson,
    DeliveryRequestStatus,
    DiscountType,
    Order,
    OrderActor,
    OrderComment,
    OrderDiscount,
    OrderItem,
    OrderLocationUpdate,
    OrderStatus,
    OrderTimeline,
    PaymentStatus,
    VehicleType,
)
from .repository import (
    BranchDeliveryRequestRepository,
    DeliveryPersonRepository,
    OrderLocationRepository,
    OrderRepository,
)
from .service import OrderService

# Repository instances
orders_repo = OrderRepository()
delivery_persons_repo = DeliveryPersonRepository()
order_locations_repo = OrderLocationRepository()
branch_delivery_requests_repo = BranchDeliveryRequestRepository()
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
    "BranchDeliveryRequest",
    "DeliveryRequestStatus",
    # Repositories
    "OrderRepository",
    "DeliveryPersonRepository",
    "OrderLocationRepository",
    "BranchDeliveryRequestRepository",
    "orders_repo",
    "delivery_persons_repo",
    "order_locations_repo",
    "branch_delivery_requests_repo",
    # Service
    "OrderService",
    "order_service",
]
