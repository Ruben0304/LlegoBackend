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
