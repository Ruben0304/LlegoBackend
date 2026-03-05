"""GraphQL type definitions for synchronization queries."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

import strawberry

from utils.s3 import generate_presigned_url


@strawberry.enum
class ImageQuality(Enum):
    """Image quality levels for download."""

    BAJA = "baja"  # Low quality (thumbnail 100x100)
    ORIGINAL = "original"  # Original quality (full size)


@strawberry.type
class CoordinatesSyncType:
    """Coordinates type for sync (same as CoordinatesType)."""

    type: str
    coordinates: List[float]


@strawberry.type
class BranchSyncType:
    """Branch type for synchronization (excludes sensitive data like managerIds)."""

    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesSyncType
    phone: str
    schedule: strawberry.scalars.JSON
    isActive: bool
    status: Optional[str] = None
    avatar: Optional[str]
    coverImage: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tipos: List[str]
    useAppMessaging: bool = True
    vehicles: List[str] = strawberry.field(default_factory=list)
    deliveryRadius: Optional[float] = None
    acceptedCurrency: Optional[str] = None
    exchangeRate: Optional[int] = None
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the branch avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None

    @strawberry.field(description="Presigned URL for the branch cover image")
    def cover_url(self) -> Optional[str]:
        if self.coverImage:
            return generate_presigned_url(self.coverImage)
        return None


@strawberry.type
class BusinessSyncType:
    """Business type for synchronization with nested branches (excludes ownerId)."""

    id: str
    name: str
    globalRating: float
    avatar: Optional[str]
    description: Optional[str]
    tags: Optional[List[str]]
    isActive: bool
    createdAt: datetime
    branches: List[BranchSyncType]

    @strawberry.field(description="Presigned URL for the business avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None


@strawberry.type
class ProductSyncType:
    """Product type for synchronization."""

    id: str
    branchId: str
    name: str
    description: str
    weight: str
    price: float
    currency: str
    image: str
    availability: bool
    categoryId: Optional[str] = None
    variantListIds: List[str] = strawberry.field(default_factory=list)
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the product image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)


@strawberry.type
class ImageUrlType:
    """Image URLs for different quality levels."""

    baja: Optional[str] = None  # Low quality (100x100 thumbnail)
    original: Optional[str] = None  # Original quality (full size)


@strawberry.type
class ImageSyncType:
    """Image metadata with URLs for different quality levels."""

    entity_id: str  # ID of the business, branch, or product
    entity_type: str  # "business", "branch", "product"
    image_path: str  # S3 path to the image
    urls: ImageUrlType  # URLs for different quality levels
