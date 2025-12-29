"""GraphQL type definitions for Business entity."""
import strawberry
from typing import Optional, List
from datetime import datetime

from utils.s3 import generate_presigned_url


@strawberry.type
class BusinessType:
    id: str
    name: str
    type: str
    ownerId: str
    globalRating: float
    avatar: Optional[str]
    coverImage: Optional[str]
    description: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tags: List[str]
    isActive: bool
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the business avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None

    @strawberry.field(description="Presigned URL for the business cover image")
    def cover_url(self) -> Optional[str]:
        if self.coverImage:
            return generate_presigned_url(self.coverImage)
        return None
