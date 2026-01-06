"""GraphQL type definitions for Branch entity."""
import strawberry
from typing import List, Optional
from datetime import datetime

from utils.s3 import generate_presigned_url


@strawberry.type
class CoordinatesType:
    type: str
    coordinates: List[float]


@strawberry.type
class BranchType:
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
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
class NearbyBranchType:
    """Branch type with distance information for geospatial queries."""
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
    createdAt: datetime
    distance_m: float  # Distance in meters from search point

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

    @strawberry.field(description="Distance in kilometers")
    def distance_km(self) -> float:
        return self.distance_m / 1000


@strawberry.type
class ScoredBranchType:
    """Branch type with scoring information for ranked results."""
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
    createdAt: datetime
    score: float  # Ranking score (0-1)
    distance_m: Optional[float] = None  # Distance in meters from user

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

    @strawberry.field(description="Distance in kilometers from user")
    def distance_km(self) -> Optional[float]:
        if self.distance_m is not None:
            return self.distance_m / 1000
        return None
