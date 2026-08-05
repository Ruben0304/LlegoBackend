"""GraphQL input types for PromotionalVideo mutations."""
import strawberry
from typing import List, Optional

from ..tutorials.types import AppTarget


@strawberry.input
class CreatePromotionalVideoInput:
    """Input for creating a new promotional video."""
    title: str
    description: str
    videoUrl: str
    duration: int
    appTarget: AppTarget
    thumbnailUrl: Optional[str] = None
    branchId: Optional[str] = None
    order: int = 0
    isActive: bool = True
    tags: List[str] = strawberry.field(default_factory=list)


@strawberry.input
class UpdatePromotionalVideoInput:
    """Input for updating an existing promotional video."""
    title: Optional[str] = None
    description: Optional[str] = None
    videoUrl: Optional[str] = None
    duration: Optional[int] = None
    appTarget: Optional[AppTarget] = None
    thumbnailUrl: Optional[str] = None
    branchId: Optional[str] = None
    order: Optional[int] = None
    isActive: Optional[bool] = None
    tags: Optional[List[str]] = None
