"""GraphQL type definitions for Orders."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, businesses_repo, payment_methods_repo, users_repo
from repositories.orders_repository import delivery_persons_repo
from schema.branches.types import BranchType, CoordinatesType
from schema.businesses.types import BusinessType
from schema.users.types import UserType
from schema.wallet.types import WalletBalanceType
from services.orders_utils import calculate_delivery_fee_h3, haversine_distance
from utils.serialization import to_strawberry_dict


# Enums
@strawberry.enum
class OrderStatusEnum(Enum):
    AWAITING_DELIVERY_ACCEPTANCE = "awaiting_delivery_acceptance"
    PENDING_PAYMENT = "pending_payment"
    PAYMENT_IN_PROGRESS = "payment_in_progress"
    PENDING_ACCEPTANCE = "pending_acceptance"
    MODIFIED_BY_STORE = "modified_by_store"
    REJECTED_BY_STORE = "rejected_by_store"
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


@strawberry.enum
class AddressTypeEnum(Enum):
    HOUSE = "house"
    APARTMENT = "apartment"
    OFFICE = "office"
    OTHER = "other"


# Types
@strawberry.type
class OrderItemType:
    productId: str
    itemId: str
    itemType: str
    name: str
    price: float
    basePrice: float
    finalPrice: float
    quantity: int
    requestDescription: Optional[str] = None
    wasModifiedByStore: bool
    comboSelections: Optional[List["OrderComboSelectionType"]] = None
    hasGift: bool = False
    discountType: Optional[str] = None
    discountValue: Optional[float] = None
    previewProducts: Optional[List["OrderPreviewProductType"]] = None

    # Private field for S3 path
    _image_path: strawberry.Private[Optional[str]]

    @strawberry.field(description="Presigned URL for the item image")
    def imageUrl(self) -> Optional[str]:
        """Generate a fresh presigned URL for the image on each query."""
        from utils.s3 import generate_presigned_url

        if not self._image_path:
            return None
        # Use 24-hour expiration for order items (86400 seconds)
        # since orders are relatively immutable after creation
        return generate_presigned_url(self._image_path, expiration=86400)

    @strawberry.field(
        description="Presigned URL for the very low quality item image (200x200)"
    )
    def imageUrlMuyBaja(self) -> Optional[str]:
        from utils.s3 import generate_image_variant_url

        if not self._image_path:
            return None
        return generate_image_variant_url(
            self._image_path, "muy_baja", expiration=86400
        )

    @strawberry.field(
        description="Presigned URL for the low quality item image (720x540)"
    )
    def imageUrlBaja(self) -> Optional[str]:
        from utils.s3 import generate_image_variant_url

        if not self._image_path:
            return None
        return generate_image_variant_url(self._image_path, "baja", expiration=86400)

    @strawberry.field(
        description="Presigned URL for the medium quality item image (1080x1350)"
    )
    def imageUrlMedia(self) -> Optional[str]:
        from utils.s3 import generate_image_variant_url

        if not self._image_path:
            return None
        return generate_image_variant_url(self._image_path, "media", expiration=86400)

    @strawberry.field(
        description="Presigned URL for the high quality item image (1440x1800)"
    )
    def imageUrlAlta(self) -> Optional[str]:
        from utils.s3 import generate_image_variant_url

        if not self._image_path:
            return None
        return generate_image_variant_url(self._image_path, "alta", expiration=86400)

    @strawberry.field(description="Presigned URL for the original item image")
    def imageUrlOriginal(self) -> Optional[str]:
        return self.imageUrl()

    @strawberry.field(description="Line total (price * quantity)")
    def line_total(self) -> float:
        return round(self.finalPrice * self.quantity, 2)


@strawberry.type
class OrderComboModifierType:
    name: str
    priceAdjustment: float


@strawberry.type
class OrderComboSelectedOptionType:
    productId: str
    name: str
    price: float
    quantity: int
    priceAdjustment: float
    modifiers: List[OrderComboModifierType]


@strawberry.type
class OrderComboSelectionType:
    slotId: str
    slotName: str
    selectedOptions: List[OrderComboSelectedOptionType]


@strawberry.type
class OrderPreviewProductType:
    productId: str
    name: str

    _image_path: strawberry.Private[Optional[str]]

    @strawberry.field(description="Presigned URL for preview product image")
    def imageUrl(self) -> Optional[str]:
        from utils.s3 import generate_presigned_url

        if not self._image_path:
            return None
        return generate_presigned_url(self._image_path, expiration=86400)


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
    # Delivery instruction fields (Uber Eats / Glovo style)
    addressType: AddressTypeEnum
    buildingName: Optional[str]
    floor: Optional[str]
    apartment: Optional[str]
    deliveryInstructions: Optional[str]

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
        addressType: str = "house",
        buildingName: Optional[str] = None,
        floor: Optional[str] = None,
        apartment: Optional[str] = None,
        deliveryInstructions: Optional[str] = None,
    ):
        self.street = street
        self.city = city
        self.reference = reference
        self.addressType = AddressTypeEnum(addressType)
        self.buildingName = buildingName
        self.floor = floor
        self.apartment = apartment
        self.deliveryInstructions = deliveryInstructions
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
    serviceCharge: float = 0.0
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
    deadlineAt: Optional[datetime] = None
    scheduledFor: Optional[datetime] = None
    resubmissionCount: int = 0

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
    _delivery_verification_code: strawberry.Private[Optional[str]] = None

    @strawberry.field(description="Order items")
    def items(self) -> List[OrderItemType]:
        order_items: List[OrderItemType] = []
        for item in self._items:
            item_id = str(item.get("itemId") or item.get("productId") or "")
            final_price = float(item.get("finalPrice", item.get("price", 0.0)))
            base_price = float(item.get("basePrice", final_price))
            raw_combo_selections = item.get("comboSelections")
            combo_selections = None
            if raw_combo_selections:
                combo_selections = []
                for selection in raw_combo_selections:
                    combo_selections.append(
                        OrderComboSelectionType(
                            slotId=str(selection.get("slotId", "")),
                            slotName=str(selection.get("slotName", "")),
                            selectedOptions=[
                                OrderComboSelectedOptionType(
                                    productId=str(opt.get("productId", "")),
                                    name=str(opt.get("name", "")),
                                    price=float(opt.get("price", 0.0)),
                                    quantity=int(opt.get("quantity", 1)),
                                    priceAdjustment=float(
                                        opt.get("priceAdjustment", 0.0)
                                    ),
                                    modifiers=[
                                        OrderComboModifierType(
                                            name=str(mod.get("name", "")),
                                            priceAdjustment=float(
                                                mod.get("priceAdjustment", 0.0)
                                            ),
                                        )
                                        for mod in opt.get("modifiers", [])
                                    ],
                                )
                                for opt in selection.get("selectedOptions", [])
                            ],
                        )
                    )
            raw_preview_products = item.get("previewProducts")
            preview_products = None
            if raw_preview_products:
                preview_products = [
                    OrderPreviewProductType(
                        productId=str(preview.get("productId", "")),
                        name=str(preview.get("name", "")),
                        _image_path=preview.get("imageUrl"),
                    )
                    for preview in raw_preview_products
                ]

            order_items.append(
                OrderItemType(
                    productId=item_id,  # Legacy alias for old clients
                    itemId=item_id,
                    itemType=str(item.get("itemType", "product")),
                    name=item["name"],
                    price=final_price,  # Legacy alias for old clients
                    basePrice=base_price,
                    finalPrice=final_price,
                    quantity=item["quantity"],
                    _image_path=item.get("imageUrl"),
                    requestDescription=item.get("requestDescription"),
                    wasModifiedByStore=item.get("wasModifiedByStore", False),
                    comboSelections=combo_selections,
                    hasGift=bool(item.get("hasGift", False)),
                    discountType=item.get("discountType"),
                    discountValue=item.get("discountValue"),
                    previewProducts=preview_products,
                )
            )
        return order_items

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
            addressType=self._delivery_address.get("addressType", "house"),
            buildingName=self._delivery_address.get("buildingName"),
            floor=self._delivery_address.get("floor"),
            apartment=self._delivery_address.get("apartment"),
            deliveryInstructions=self._delivery_address.get("deliveryInstructions"),
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

    @strawberry.field(
        description=(
            "Codigo de verificacion de entrega. Solo visible para el cliente "
            "dueno del pedido mientras esta en camino."
        )
    )
    def delivery_verification_code(self, info: Info) -> Optional[str]:
        user_id = None
        if isinstance(info.context, dict):
            user_id = info.context.get("user_id")
        else:
            user_id = getattr(info.context, "user_id", None)

        if not user_id or str(user_id) != str(self.customerId):
            return None
        if self.status not in {OrderStatusEnum.ON_THE_WAY, OrderStatusEnum.READY_FOR_PICKUP}:
            return None
        return self._delivery_verification_code

    @strawberry.field(description="Customer who placed the order")
    async def customer(self) -> UserType:
        user = await users_repo.get_by_id(self.customerId)
        if not user:
            raise Exception(f"Customer not found: {self.customerId}")
        return UserType(
            **{
                **to_strawberry_dict(
                    user,
                    exclude={"password", "location", "wallet", "walletStatus"},
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
        return BusinessType(**to_strawberry_dict(business))

    @strawberry.field(description="Assigned delivery person")
    async def delivery_person(self) -> Optional[DeliveryPersonType]:
        if not self.deliveryPersonId:
            return None
        dp = await delivery_persons_repo.get_by_id(self.deliveryPersonId)
        if dp:
            return DeliveryPersonType(
                id=str(dp.id),
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

    @strawberry.field(description="Whether order can be edited by customer")
    def is_editable(self) -> bool:
        return self.status in {
            OrderStatusEnum.MODIFIED_BY_STORE,
            OrderStatusEnum.REJECTED_BY_STORE,
        }

    @strawberry.field(description="Whether order can be cancelled")
    def can_cancel(self) -> bool:
        return self.status in {
            OrderStatusEnum.PENDING_ACCEPTANCE,
            OrderStatusEnum.PENDING_PAYMENT,
            OrderStatusEnum.MODIFIED_BY_STORE,
            OrderStatusEnum.REJECTED_BY_STORE,
        }

    @strawberry.field(description="Human-readable payment method name")
    async def paymentMethodName(self) -> Optional[str]:
        pm = await payment_methods_repo.get_by_code(self.paymentMethod)
        return pm.name if pm else None

    @strawberry.field(description="Customer-facing status")
    def customer_visible_status(self) -> OrderStatusEnum:
        if self.status in {
            OrderStatusEnum.READY_FOR_PICKUP,
            OrderStatusEnum.ON_THE_WAY,
        }:
            return OrderStatusEnum.ON_THE_WAY
        return self.status

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
    fallback_coords = (
        order.pickupAddress.coordinates.model_dump()
        if order.pickupAddress and order.pickupAddress.coordinates
        else {"type": "Point", "coordinates": [0.0, 0.0]}
    )
    delivery_address_payload = (
        order.deliveryAddress.model_dump()
        if order.deliveryAddress
        else {
            "street": order.pickupAddress.street
            if order.pickupAddress
            else "Recogida en tienda",
            "city": None,
            "reference": "pickup",
            "coordinates": fallback_coords,
            "addressType": "other",
            "buildingName": None,
            "floor": None,
            "apartment": None,
            "deliveryInstructions": None,
        }
    )

    return OrderType(
        id=str(order.id),
        orderNumber=order.orderNumber,
        customerId=str(order.customerId),
        branchId=str(order.branchId),
        businessId=str(order.businessId),
        subtotal=order.subtotal,
        deliveryFee=order.deliveryFee,
        serviceCharge=order.serviceCharge,
        deliveryMode=order.deliveryMode,
        total=order.total,
        currency=order.currency,
        status=OrderStatusEnum(order.status.value),
        paymentMethod=order.paymentMethod,
        paymentStatus=PaymentStatusEnum(order.paymentStatus.value),
        createdAt=order.createdAt,
        updatedAt=order.updatedAt,
        lastStatusAt=order.lastStatusAt,
        deliveryPersonId=str(order.deliveryPersonId)
        if order.deliveryPersonId
        else None,
        deliveryZoneId=order.deliveryZoneId,
        estimatedDeliveryTime=order.estimatedDeliveryTime,
        paymentId=order.paymentId,
        currentPaymentAttemptId=str(order.currentPaymentAttemptId)
        if order.currentPaymentAttemptId
        else None,
        paidAt=order.paidAt,
        deadlineAt=order.deadlineAt,
        scheduledFor=order.scheduledFor,
        resubmissionCount=order.resubmissionCount,
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
        _delivery_address=delivery_address_payload,
        _pickup_address=order.pickupAddress.model_dump()
        if order.pickupAddress
        else None,
        _timeline=[t.model_dump() for t in order.timeline],
        _comments=[c.model_dump() for c in order.comments],
        _delivery_verification_code=order.deliveryVerificationCode,
    )


@strawberry.type
class OrdersConnectionType:
    orders: List[OrderType]
    totalCount: int
    hasMore: bool


@strawberry.enum
class DeliveredOrderFinalStatusEnum(Enum):
    DELIVERED = "delivered"
    DISPUTED = "disputed"
    REVERSED = "reversed"
    FRAUD_HIDDEN = "fraud_hidden"


@strawberry.type
class DeliveredOrderType:
    orderId: str
    orderNumber: str
    deliveredAt: datetime
    merchantName: str
    customerDisplayName: str
    addressSummary: str
    city: Optional[str] = None
    visibleAmount: float
    currency: str
    finalStatus: DeliveredOrderFinalStatusEnum
    hasDeliveryEvidence: bool


@strawberry.type
class DeliveredOrdersEdgeType:
    cursor: str
    node: DeliveredOrderType


@strawberry.type
class DeliveredOrdersPageInfoType:
    hasNextPage: bool
    endCursor: Optional[str] = None


@strawberry.type
class DeliveredOrdersConnectionType:
    edges: List[DeliveredOrdersEdgeType]
    pageInfo: DeliveredOrdersPageInfoType
    totalCount: int


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
    totalQuantity: int
    totalRevenue: float

    # Private field for S3 path
    _image_path: strawberry.Private[str]

    @strawberry.field(description="Presigned URL for the product image")
    def imageUrl(self) -> str:
        """Generate a fresh presigned URL for the image on each query."""
        from utils.s3 import generate_presigned_url

        # Use 24-hour expiration for dashboard stats (86400 seconds)
        return generate_presigned_url(self._image_path, expiration=86400)

    @strawberry.field(
        description="Presigned URL for the very low quality product image (200x200)"
    )
    def imageUrlMuyBaja(self) -> str:
        from utils.s3 import generate_image_variant_url

        return generate_image_variant_url(
            self._image_path, "muy_baja", expiration=86400
        )

    @strawberry.field(
        description="Presigned URL for the low quality product image (720x540)"
    )
    def imageUrlBaja(self) -> str:
        from utils.s3 import generate_image_variant_url

        return generate_image_variant_url(self._image_path, "baja", expiration=86400)

    @strawberry.field(
        description="Presigned URL for the medium quality product image (1080x1350)"
    )
    def imageUrlMedia(self) -> str:
        from utils.s3 import generate_image_variant_url

        return generate_image_variant_url(self._image_path, "media", expiration=86400)

    @strawberry.field(
        description="Presigned URL for the high quality product image (1440x1800)"
    )
    def imageUrlAlta(self) -> str:
        from utils.s3 import generate_image_variant_url

        return generate_image_variant_url(self._image_path, "alta", expiration=86400)

    @strawberry.field(description="Presigned URL for the original product image")
    def imageUrlOriginal(self) -> str:
        return self.imageUrl()


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
class OrderTrackingStreamPayload:
    """Real-time order tracking payload for WebSocket subscriptions."""

    estimatedMinutes: Optional[int] = None
    distanceKm: Optional[float] = None
    deliveryPersonLocation: Optional[CoordinatesType] = None

    # Nested order info
    @strawberry.field(description="Order summary")
    def order(self) -> "OrderSummaryType":
        return self._order

    def __init__(
        self,
        order_id: str,
        order_status: OrderStatusEnum,
        estimated_minutes_remaining: Optional[int],
        estimatedMinutes: Optional[int] = None,
        distanceKm: Optional[float] = None,
        deliveryPersonLocation: Optional[CoordinatesType] = None,
    ):
        self.estimatedMinutes = estimatedMinutes
        self.distanceKm = distanceKm
        self.deliveryPersonLocation = deliveryPersonLocation
        self._order = OrderSummaryType(
            id=order_id,
            status=order_status,
            estimatedMinutesRemaining=estimated_minutes_remaining,
        )


@strawberry.type
class OrderSummaryType:
    """Minimal order info for tracking stream."""

    id: str
    status: OrderStatusEnum
    estimatedMinutesRemaining: Optional[int] = None


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
                id=str(dp.id),
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
        id=str(req.id),
        deliveryPersonId=str(req.deliveryPersonId),
        branchId=str(req.branchId),
        status=DeliveryRequestStatusEnum(req.status.value),
        message=req.message,
        respondedBy=str(req.respondedBy) if req.respondedBy else None,
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
        branchId=str(branch.id),
        branchName=branch.name,
    )
