"""GraphQL type definitions for Tutorial entity."""
import strawberry
from typing import List, Optional
from datetime import datetime
from enum import Enum
from strawberry.types import Info

from utils.s3 import get_public_url


@strawberry.enum
class AppTarget(Enum):
    """Target app for tutorial."""
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    BOTH = "both"


@strawberry.type
class TutorialType:
    """Tutorial GraphQL type."""
    id: str
    title: str
    description: str
    videoUrl: str
    duration: int
    appTarget: AppTarget
    thumbnailUrl: Optional[str]
    order: int
    isActive: bool
    tags: List[str]
    createdAt: datetime
    updatedAt: Optional[datetime]

    @strawberry.field(description="Public URL for the tutorial video")
    def video_url_signed(self) -> str:
        return get_public_url(self.videoUrl)

    @strawberry.field(description="Public URL for the tutorial thumbnail")
    def thumbnail_url_signed(self) -> Optional[str]:
        return get_public_url(self.thumbnailUrl) if self.thumbnailUrl else None
