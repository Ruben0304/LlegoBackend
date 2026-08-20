"""GraphQL type definitions for User entity."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import strawberry
from strawberry.scalars import JSON

from schema.wallet.types import WalletBalanceType
from utils.s3 import get_public_url


@strawberry.type
class SavedAddressType:
    """A saved delivery address in the user's profile."""

    id: str
    label: str
    street: str
    city: Optional[str]
    reference: Optional[str]
    addressType: str
    buildingName: Optional[str]
    floor: Optional[str]
    apartment: Optional[str]
    deliveryInstructions: Optional[str]
    latitude: float
    longitude: float


@strawberry.type
class UserType:
    id: str
    name: str
    email: str
    username: str
    phone: Optional[str]
    role: str
    avatar: Optional[str]
    businessIds: List[str]
    branchIds: List[str]
    businessAccessIds: List[str]
    createdAt: datetime
    authProvider: str
    providerUserId: Optional[str]
    applePrivateEmail: Optional[str]
    wallet: WalletBalanceType
    walletStatus: str = "active"
    isPro: bool = False
    location: Optional[JSON] = (
        None  # GeoJSON: {"type": "Point", "coordinates": [lon, lat]}
    )
    aiConsultasLimit: Optional[JSON] = None
    # Saved delivery addresses (Uber Eats / Glovo style)
    savedAddresses: List[SavedAddressType] = strawberry.field(default_factory=list)
    defaultAddressId: Optional[str] = None
    deliveredOrdersCount: int = 0
    scheduledDeletionAt: Optional[datetime] = None
    lastSeenAt: Optional[datetime] = None

    @strawberry.field(description="URL firmada del avatar del usuario")
    def avatar_url(self) -> Optional[str]:
        """Generate presigned URL for user avatar."""
        if self.avatar:
            return get_public_url(self.avatar)
        return None


@strawberry.type
class UserSegmentMetricsType:
    """Registered vs. active count for one app segment."""

    total: int
    active: int


@strawberry.type
class DailyCountType:
    day: str
    count: int


@strawberry.type
class UserMetricsType:
    """Platform user metrics, split by which app a user belongs to.

    Segments overlap by design: a courier or business owner can also order as a
    customer. `customersOnly` is therefore the remainder (users who are neither),
    which keeps the three segment totals summing to `totalUsers`, and
    `multiRoleUsers` exposes the courier/business intersection.
    """

    totalUsers: int
    activeUsers: int
    newUsersInPeriod: int
    customersOnly: UserSegmentMetricsType
    couriers: UserSegmentMetricsType
    businesses: UserSegmentMetricsType
    multiRoleUsers: int
    signupsByDay: List[DailyCountType]
    activeDays: int


@strawberry.enum
class UserSegmentEnum(Enum):
    """Which metrics card the admin drilled into."""

    ALL = "all"
    ACTIVE = "active"
    NEW = "new"
    CUSTOMERS_ONLY = "customers_only"
    COURIERS = "couriers"
    BUSINESSES = "businesses"


@strawberry.type
class AdminUserRowType:
    """A user as shown in the admin drill-down list.

    Built field by field rather than by unpacking the domain model, so adding a
    field to `User` can't silently change what the admin panel exposes — and
    `password` can never leak in by accident.
    """

    id: str
    name: str
    email: str
    username: str
    phone: Optional[str] = None
    createdAt: Optional[datetime] = None
    lastSeenAt: Optional[datetime] = None
    authProvider: str = "local"
    walletStatus: str = "active"
    deliveredOrdersCount: int = 0
    scheduledDeletionAt: Optional[datetime] = None
    # Which apps this user belongs to — the same joins the metrics use.
    isCourier: bool = False
    isBusiness: bool = False
    isActive: bool = False

    _avatar_path: strawberry.Private[Optional[str]] = None

    @strawberry.field(description="URL firmada del avatar")
    def avatarUrl(self) -> Optional[str]:
        if not self._avatar_path:
            return None
        return get_public_url(self._avatar_path)


@strawberry.type
class AdminUsersConnectionType:
    rows: List[AdminUserRowType]
    totalCount: int
    hasMore: bool
