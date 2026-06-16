"""GraphQL type definitions for Business entity."""
import strawberry
from typing import Optional, List
from datetime import datetime

from utils.s3 import get_public_image_variant_url, get_public_url


@strawberry.type
class BusinessType:
    id: str
    name: str
    ownerId: str
    globalRating: float
    avatar: Optional[str]
    description: Optional[str]
    tags: Optional[List[str]]
    isActive: bool
    approvalStatus: str
    rejectionReason: Optional[str]
    approvedAt: Optional[datetime]
    rejectedAt: Optional[datetime]
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the business avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return get_public_url(self.avatar)
        return None

    @strawberry.field(
        description="Presigned URL for low quality business avatar (with fallback to original)"
    )
    def avatar_url_baja(self) -> Optional[str]:
        if self.avatar:
            return get_public_image_variant_url(self.avatar, "avatar_baja")
        return None

    @strawberry.field(
        description="Presigned URL for high quality business avatar (with fallback to original)"
    )
    def avatar_url_alta(self) -> Optional[str]:
        if self.avatar:
            return get_public_image_variant_url(self.avatar, "avatar_alta")
        return None
