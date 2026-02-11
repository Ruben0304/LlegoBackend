"""GraphQL type definitions for Orders."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

import strawberry

from repositories.orders_repository import delivery_persons_repo
from services.orders_utils import calculate_delivery_fee_h3, haversine_distance
from repositories import branches_repo, businesses_repo, users_repo
from schema.branches.types import BranchType, CoordinatesType
from schema.businesses.types import BusinessType
from schema.users.types import UserType
from schema.wallet.types import WalletBalanceType


# Enums
@strawberry.enum
class OrderStatusEnum(Enum):
    PENDING_ACCEPTANCE = "pending_acceptance"
    MODIFIED_BY_STORE = "modified_by_store"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY_FOR_PICKUP = "ready_for_pickup"
    ON_THE_WAY = "on_the_way"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@strawberry.enum
class PaymentStatusEnum(Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.enum
class DiscountTypeEnum(Enum):
    PREMIUM = "premium"
    LEVEL = "level"
    PROMO = "promo"


@strawberry.enum
class OrderActorEnum(Enum):
    CUSTOMER = "customer"
    BUSINESS = "business"
    SYSTEM = "system"
    DELIVERY = "delivery"


@strawberry.enum
class VehicleTypeEnum(Enum):
    MOTO = "moto"
    BICICLETA = "bicicleta"
    AUTO = "auto"
    A_PIE = "a_pie"


# Types
@strawberry.type
class OrderItemType:
    productId: str
    name: str
    price: float
    quantity: int
    imageUrl: str
    wasModifiedByStore: bool

    @strawberry.field(description="Line total (price * quantity)")
    def line_total(self) -> float:
        return round(self.price * self.quantity, 2)


@strawberry.type
class OrderDiscountType:
    id: str
    title: str
    amount: float
    type: DiscountTypeEnum


@strawberry.type
class DeliveryAddressType:
    street: str
    city: Optional[str]
    reference: Optional[str]

    @strawberry.field(description="Delivery coordinates")
    def coordinates(self) -> CoordinatesType:
        # This will be set from the parent resolver
        return self._coordinates

    def __init__(
        self,
        street: str,
        city: Optional[str],
        reference: Optional[str],
        coordinates: dict,
    ):
        self.street = street
        self.city = city
        self.reference = reference
        self._coordinates = CoordinatesType(
            type=coordinates.get("type", "Point"),
            coordinates=coordinates.get("coordinates", []),
        )


@strawberry.type
class PickupAddressType:
    street: Optional[str]

    @strawberry.field(description="Pickup coordinates")
    def coordinates(self) -> CoordinatesType:
        return self._coordinates

    def __init__(self, street: Optional[str], coordinates: dict):
        self.street = street
        self._coordinates = CoordinatesType(
            type=coordinates.get("type", "Point"),
            coordinates=coordinates.get("coordinates", []),
        )


@strawberry.type
class OrderTimelineType:
    status: OrderStatusEnum
    timestamp: datetime
    message: str
    actor: OrderActorEnum


@strawberry.type
class OrderCommentType:
    id: str
    author: OrderActorEnum
    message: str
    timestamp: datetime


@strawberry.type
class DeliveryPersonType:
    id: str
    name: str
    phone: str
    rating: float
    totalDeliveries: int
    vehicleType: VehicleTypeEnum
    vehiclePlate: Optional[str]
    profileImageUrl: Optional[str]
    isOnline: bool

    @strawberry.field(description="Current location of delivery person")
    def current_location(self) -> Optional[CoordinatesType]:
        if self._current_location:
            return CoordinatesType(
                type=self._current_location.get("type", "Point"),
                coordinates=self._current_location.get("coordinates", []),
            )
        return None

    def __init__(
        self,
        id: str,
        name: str,
        phone: str,
        rating: float,
        totalDeliveries: int,
        vehicleType: str,
        vehiclePlate: Optional[str],
        profileImageUrl: Optional[str],
        isOnline: bool,
        currentLocation: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.phone = phone
        self.rating = rating
        self.totalDeliveries = totalDeliveries
        self.vehicleType = VehicleTypeEnum(vehicleType)
        self.vehiclePlate = vehiclePlate
        self.profileImageUrl = profileImageUrl
        self.isOnline = isOnline
        self._current_location = currentLocation


@strawberry.type
class OrderType:
    id: str
    orderNumber: str
    customerId: str
    branchId: str
    businessId: str
    subtotal: float
    deliveryFee: float
    deliveryMode: str
    total: float
    currency: str
    status: OrderStatusEnum
    paymentMethod: str
    paymentStatus: PaymentStatusEnum
    createdAt: datetime
    updatedAt: datetime
    lastStatusAt: datetime
    deliveryPersonId: Optional[str] = None
    deliveryZoneId: Optional[str] = None
    estimatedDeliveryTime: Optional[datetime] = None
    paymentId: Optional[str] = None
    currentPaymentAttemptId: Optional[str] = None
    paidAt: Optional[datetime] = None

    # Delivery tracking timestamps & metrics
    assignedAt: Optional[datetime] = None
    pickedUpAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    deliveryDistanceKm: Optional[float] = None
    deliveryDurationMin: Optional[int] = None
    deliveryEarnings: Optional[float] = None

    rating: Optional[int] = None
    ratingComment: Optional[str] = None

    # Internal fields for resolvers
    _items: strawberry.Private[List[dict]]
    _discounts: strawberry.Private[List[dict]]
    _delivery_address: strawberry.Private[dict]
    _pickup_address: strawberry.Private[Optional[dict]]
    _timeline: strawberry.Private[List[dict]]
    _comments: strawberry.Private[List[dict]]

    @strawberry.field(description="Order items")
    def items(self) -> List[OrderItemType]:
        return [
            OrderItemType(
                productId=item["productId"],
                name=item["name"],
                price=item["price"],
                quantity=item["quantity"],
                imageUrl=item["imageUrl"],
                wasModifiedByStore=item.get("wasModifiedByStore", False),
            )
            for item in self._items
        ]

    @strawberry.field(description="Applied discounts")
    def discounts(self) -> List[OrderDiscountType]:
        return [
            OrderDiscountType(
                id=d["id"],
                title=d["title"],
                amount=d["amount"],
                type=DiscountTypeEnum(d["type"]),
            )
            for d in self._discounts
        ]

    @strawberry.field(description="Delivery address")
    def delivery_address(self) -> DeliveryAddressType:
        return DeliveryAddressType(
            street=self._delivery_address["street"],
            city=self._delivery_address.get("city"),
            reference=self._delivery_address.get("reference"),
            coordinates=self._delivery_address.get("coordinates", {}),
        )

    @strawberry.field(description="Pickup address (branch location)")
    def pickup_address(self) -> Optional[PickupAddressType]:
        if not self._pickup_address:
            return None
        return PickupAddressType(
            street=self._pickup_address.get("street"),
            coordinates=self._pickup_address.get("coordinates", {}),
        )

    @strawberry.field(description="Order timeline")
    def timeline(self) -> List[OrderTimelineType]:
        return [
            OrderTimelineType(
                status=OrderStatusEnum(t["status"]),
                timestamp=t["timestamp"],
                message=t["message"],
                actor=OrderActorEnum(t["actor"]),
            )
            for t in self._timeline
        ]

    @strawberry.field(description="Order comments")
    def comments(self) -> List[OrderCommentType]:
        return [
            OrderCommentType(
                id=c["id"],
                author=OrderActorEnum(c["author"]),
                message=c["message"],
                timestamp=c["timestamp"],
            )
            for c in self._comments
        ]

    @strawberry.field(description="Customer who placed the order")
    async def customer(self) -> UserType:
        user = await users_repo.get_by_id(self.customerId)
        if not user:
            raise Exception(f"Customer not found: {self.customerId}")
        return UserType(
            **{
                **user.model_dump(
                    exclude={"password", "location", "wallet", "walletStatus"}
                ),
                "wallet": WalletBalanceType(
                    local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
                ),
                "walletStatus": user.walletStatus,
            }
        )

    @strawberry.field(description="Branch preparing the order")
    async def branch(self) -> BranchType:
        from schema.branches.utils import branch_to_dict

        branch = await branches_repo.get_by_id(self.branchId)
        if not branch:
            raise Exception(f"Branch not found: {self.branchId}")
        return BranchType(**branch_to_dict(branch))

    @strawberry.field(description="Business owning the branch")
    async def business(self) -> BusinessType:
        business = await businesses_repo.get_by_id(self.businessId)
        if not business:
            raise Exception(f"Business not found: {self.businessId}")
        return BusinessType(**business.model_dump())

    @strawberry.field(description="Assigned delivery person")
    async def delivery_person(self) -> Optional[DeliveryPersonType]:
        if not self.deliveryPersonId:
            return None
        dp = await delivery_persons_repo.get_by_id(self.deliveryPersonId)
        if dp:
            return DeliveryPersonType(
                id=dp.id,
                name=dp.name,
                phone=dp.phone,
                rating=dp.rating,
                totalDeliveries=dp.totalDeliveries,
                vehicleType=dp.vehicleType.value,
                vehiclePlate=dp.vehiclePlate,
                profileImageUrl=dp.profileImageUrl,
                isOnline=dp.isOnline,
                currentLocation=dp.currentLocation.model_dump()
                if dp.currentLocation
                else None,
            )
        return None

    @strawberry.field(description="Whether order can be edited by customer")
    def is_editable(self) -> bool:
        return self.status == OrderStatusEnum.MODIFIED_BY_STORE

    @strawberry.field(description="Whether order can be cancelled")
    def can_cancel(self) -> bool:
        non_cancellable = [OrderStatusEnum.DELIVERED, OrderStatusEnum.CANCELLED]
        return self.status not in non_cancellable

    @strawberry.field(description="Estimated minutes remaining for delivery")
    def estimated_minutes_remaining(self) -> Optional[int]:
        if self.estimatedDeliveryTime:
            from datetime import datetime

            remaining = (
                self.estimatedDeliveryTime - datetime.utcnow()
            ).total_seconds() / 60
            return max(0, int(remaining))
        return None


def order_to_type(order) -> OrderType:
    """Convert Order model to OrderType."""
    return OrderType(
        id=order.id,
        orderNumber=order.orderNumber,
        customerId=order.customerId,
        branchId=order.branchId,
        businessId=order.businessId,
        subtotal=order.subtotal,
        deliveryFee=order.deliveryFee,
        deliveryMode=order.deliveryMode,
        total=order.total,
        currency=order.currency,
        status=OrderStatusEnum(order.status.value),
        paymentMethod=order.paymentMethod,
        paymentStatus=PaymentStatusEnum(order.paymentStatus.value),
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
        lastStatusAt=order.lastStatusAt,
        deliveryPersonId=order.deliveryPersonId,
        deliveryZoneId=order.deliveryZoneId,
        estimatedDeliveryTime=order.estimatedDeliveryTime,
        paymentId=order.paymentId,
        currentPaymentAttemptId=order.currentPaymentAttemptId,
        paidAt=order.paidAt,
        assignedAt=order.assignedAt,
        pickedUpAt=order.pickedUpAt,
        completedAt=order.completedAt,
        deliveryDistanceKm=order.deliveryDistanceKm,
        deliveryDurationMin=order.deliveryDurationMin,
        deliveryEarnings=order.deliveryEarnings,
        rating=order.rating,
        ratingComment=order.ratingComment,
        _items=[item.model_dump() for item in order.items],
        _discounts=[d.model_dump() for d in order.discounts],
        _delivery_address=order.deliveryAddress.model_dump(),
        _pickup_address=order.pickupAddress.model_dump()
        if order.pickupAddress
        else None,
        _timeline=[t.model_dump() for t in order.timeline],
        _comments=[c.model_dump() for c in order.comments],
    )


@strawberry.type
class OrdersConnectionType:
    orders: List[OrderType]
    totalCount: int
    hasMore: bool


@strawberry.type
class OrderStatsType:
    totalOrders: int
    completedOrders: int
    cancelledOrders: int
    totalRevenue: float
    averageOrderValue: float
    averageDeliveryTime: int


@strawberry.type
class TopProductType:
    productId: str
    name: str
    imageUrl: str
    totalQuantity: int
    totalRevenue: float


@strawberry.type
class DashboardStatsType:
    totalRevenue: float
    completedOrders: int
    cancelledOrders: int
    topProducts: List[TopProductType]


@strawberry.type
class OrderTrackingType:
    order: OrderType
    storeLocation: CoordinatesType
    deliveryLocation: CoordinatesType
    deliveryPersonLocation: Optional[CoordinatesType] = None
    estimatedMinutes: Optional[int] = None
    distanceKm: Optional[float] = None
    routePolyline: Optional[str] = None


@strawberry.type
class DeliveryLocationUpdateType:
    orderId: str
    location: CoordinatesType
    timestamp: datetime
    estimatedMinutesRemaining: Optional[int] = None
    distanceRemainingKm: Optional[float] = None


@strawberry.type
class DeliveryFeeEstimateType:
    """Estimación del precio de envío antes de crear el pedido."""

    deliveryFee: float
    currency: str
    distanceKm: float
    zoneName: Optional[str]
    h3Index: Optional[str]
    branchId: str
    branchName: str


@strawberry.enum
class DeliveryRequestStatusEnum(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@strawberry.type
class BranchDeliveryRequestType:
    id: str
    deliveryPersonId: str
    branchId: str
    status: DeliveryRequestStatusEnum
    message: Optional[str]
    respondedBy: Optional[str]
    respondedAt: Optional[datetime]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Detalles de la sucursal")
    async def branch(self) -> Optional[BranchType]:
        from schema.branches.utils import branch_to_dict

        branch = await branches_repo.get_by_id(self.branchId)
        return BranchType(**branch_to_dict(branch)) if branch else None

    @strawberry.field(description="Detalles del repartidor")
    async def delivery_person(self) -> Optional[DeliveryPersonType]:
        dp = await delivery_persons_repo.get_by_id(self.deliveryPersonId)
        if dp:
            return DeliveryPersonType(
                id=dp.id,
                name=dp.name,
                phone=dp.phone or "",
                rating=dp.rating,
                totalDeliveries=dp.totalDeliveries,
                vehicleType=dp.vehicleType.value,
                vehiclePlate=dp.vehiclePlate,
                profileImageUrl=dp.profileImageUrl,
                isOnline=dp.isOnline,
                currentLocation=dp.currentLocation.model_dump()
                if dp.currentLocation
                else None,
            )
        return None


def branch_delivery_request_to_type(req) -> BranchDeliveryRequestType:
    return BranchDeliveryRequestType(
        id=req.id,
        deliveryPersonId=req.deliveryPersonId,
        branchId=req.branchId,
        status=DeliveryRequestStatusEnum(req.status.value),
        message=req.message,
        respondedBy=req.respondedBy,
        respondedAt=req.respondedAt,
        createdAt=req.createdAt,
        updatedAt=req.updatedAt,
    )


async def estimate_delivery_fee(
    branch_id: str,
    latitude: float,
    longitude: float,
    subtotal: float = 0.0,
) -> DeliveryFeeEstimateType:
    """Calculate delivery fee estimate for a branch and delivery address."""
    branch = await branches_repo.get_by_id(branch_id)
    if not branch:
        raise ValueError("Sucursal no encontrada")

    branch_coords = (
        branch.coordinates.coordinates[0],
        branch.coordinates.coordinates[1],
    )
    delivery_coords = (longitude, latitude)

    fee, h3_index = await calculate_delivery_fee_h3(
        branch_coords, delivery_coords, subtotal
    )

    distance_km = haversine_distance(branch_coords, delivery_coords)

    # Get zone name if matched
    zone_name: Optional[str] = None
    if h3_index:
        from clients.mongodb_client import get_database

        db = get_database()
        zone = await db.delivery_zones.find_one({"h3Index": h3_index})
        if zone:
            zone_name = zone.get("name")

    return DeliveryFeeEstimateType(
        deliveryFee=fee,
        currency="CUP",
        distanceKm=round(distance_km, 2),
        zoneName=zone_name,
        h3Index=h3_index,
        branchId=branch.id,
        branchName=branch.name,
    )
