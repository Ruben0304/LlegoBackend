"""GraphQL type definitions for Orders."""
import strawberry
from datetime import datetime
from typing import Optional, List
from enum import Enum

from schema.users.types import UserType
from schema.branches.types import BranchType, CoordinatesType
from schema.businesses.types import BusinessType
from repositories import users_repo, branches_repo, businesses_repo
from orders import delivery_persons_repo


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
    
    def __init__(self, street: str, city: Optional[str], reference: Optional[str], coordinates: dict):
        self.street = street
        self.city = city
        self.reference = reference
        self._coordinates = CoordinatesType(
            type=coordinates.get("type", "Point"),
            coordinates=coordinates.get("coordinates", [])
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
                coordinates=self._current_location.get("coordinates", [])
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
        currentLocation: Optional[dict] = None
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
    total: float
    currency: str
    status: OrderStatusEnum
    paymentMethod: str
    paymentStatus: PaymentStatusEnum
    createdAt: datetime
    updatedAt: datetime
    lastStatusAt: datetime
    deliveryPersonId: Optional[str] = None
    estimatedDeliveryTime: Optional[datetime] = None
    paymentId: Optional[str] = None
    rating: Optional[int] = None
    ratingComment: Optional[str] = None
    
    # Internal fields for resolvers
    _items: strawberry.Private[List[dict]]
    _discounts: strawberry.Private[List[dict]]
    _delivery_address: strawberry.Private[dict]
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
                wasModifiedByStore=item.get("wasModifiedByStore", False)
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
                type=DiscountTypeEnum(d["type"])
            )
            for d in self._discounts
        ]
    
    @strawberry.field(description="Delivery address")
    def delivery_address(self) -> DeliveryAddressType:
        return DeliveryAddressType(
            street=self._delivery_address["street"],
            city=self._delivery_address.get("city"),
            reference=self._delivery_address.get("reference"),
            coordinates=self._delivery_address.get("coordinates", {})
        )
    
    @strawberry.field(description="Order timeline")
    def timeline(self) -> List[OrderTimelineType]:
        return [
            OrderTimelineType(
                status=OrderStatusEnum(t["status"]),
                timestamp=t["timestamp"],
                message=t["message"],
                actor=OrderActorEnum(t["actor"])
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
                timestamp=c["timestamp"]
            )
            for c in self._comments
        ]

    @strawberry.field(description="Customer who placed the order")
    async def customer(self) -> UserType:
        user = await users_repo.get_by_id(self.customerId)
        if not user:
            raise Exception(f"Customer not found: {self.customerId}")
        return UserType(**{**user.model_dump(exclude={'password', 'location'}), '_wallet': user.wallet, '_wallet_status': user.walletStatus})
    
    @strawberry.field(description="Branch preparing the order")
    async def branch(self) -> BranchType:
        from schema.branches.types import BranchTipo
        branch = await branches_repo.get_by_id(self.branchId)
        if not branch:
            raise Exception(f"Branch not found: {self.branchId}")
        return BranchType(
            **{
                **branch.model_dump(),
                'coordinates': CoordinatesType(**branch.coordinates.model_dump()),
                'tipos': [BranchTipo(t) for t in (branch.tipos or [])]
            }
        )
    
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
                currentLocation=dp.currentLocation.model_dump() if dp.currentLocation else None
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
            remaining = (self.estimatedDeliveryTime - datetime.utcnow()).total_seconds() / 60
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
        total=order.total,
        currency=order.currency,
        status=OrderStatusEnum(order.status.value),
        paymentMethod=order.paymentMethod,
        paymentStatus=PaymentStatusEnum(order.paymentStatus.value),
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
        lastStatusAt=order.lastStatusAt,
        deliveryPersonId=order.deliveryPersonId,
        estimatedDeliveryTime=order.estimatedDeliveryTime,
        paymentId=order.paymentId,
        rating=order.rating,
        ratingComment=order.ratingComment,
        _items=[item.model_dump() for item in order.items],
        _discounts=[d.model_dump() for d in order.discounts],
        _delivery_address=order.deliveryAddress.model_dump(),
        _timeline=[t.model_dump() for t in order.timeline],
        _comments=[c.model_dump() for c in order.comments]
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
