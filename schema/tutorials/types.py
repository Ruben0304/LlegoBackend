"""GraphQL type definitions for Tutorial entity."""
import strawberry
from typing import List, Optional
from datetime import datetime
from enum import Enum
from strawberry.types import Info

from utils.s3 import generate_presigned_url


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

    @strawberry.field(description="Presigned URL for the tutorial video")
    def video_url_signed(self) -> str:
        """Generate presigned URL for video."""
        return generate_presigned_url(self.videoUrl)

    @strawberry.field(description="Presigned URL for the tutorial thumbnail")
    def thumbnail_url_signed(self) -> Optional[str]:
        """Generate presigned URL for thumbnail."""
        if self.thumbnailUrl:
            return generate_presigned_url(self.thumbnailUrl)
        return None
