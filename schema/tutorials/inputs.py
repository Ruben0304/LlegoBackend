"""GraphQL input types for Tutorial mutations."""
import strawberry
from typing import List, Optional

from .types import AppTarget


@strawberry.input
class CreateTutorialInput:
    """Input for creating a new tutorial."""
    title: str
    description: str
    videoUrl: str
    duration: int
    appTarget: AppTarget
    thumbnailUrl: Optional[str] = None
    order: int = 0
    isActive: bool = True
    tags: List[str] = strawberry.field(default_factory=list)


@strawberry.input
class UpdateTutorialInput:
    """Input for updating an existing tutorial."""
    title: Optional[str] = None
    description: Optional[str] = None
    videoUrl: Optional[str] = None
    duration: Optional[int] = None
    appTarget: Optional[AppTarget] = None
    thumbnailUrl: Optional[str] = None
    order: Optional[int] = None
    isActive: Optional[bool] = None
    tags: Optional[List[str]] = None
