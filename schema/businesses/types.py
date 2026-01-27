"""GraphQL type definitions for Business entity."""
import strawberry
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from utils.s3 import generate_presigned_url

if TYPE_CHECKING:
    from schema.branches.types import BranchType


@strawberry.type
class BusinessType:
    id: str
    name: str
    ownerId: str
    globalRating: float
    avatar: Optional[str]
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


@strawberry.type
class BusinessWithBranchesType:
    """Business type with nested branches for optimized queries."""
    id: str
    name: str
    ownerId: str
    globalRating: float
    avatar: Optional[str]
    description: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tags: List[str]
    isActive: bool
    createdAt: datetime
    branches: List["BranchType"]

    @strawberry.field(description="Presigned URL for the business avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None
