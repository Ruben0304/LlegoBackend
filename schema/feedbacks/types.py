"""GraphQL type definitions for Feedback entity."""
import strawberry
from datetime import datetime
from typing import Optional
from enum import Enum


@strawberry.enum
class FeedbackTypeEnum(Enum):
    """Types of feedback."""
    BUG = "BUG"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    IMPROVEMENT = "IMPROVEMENT"


@strawberry.enum
class FeedbackStatusEnum(Enum):
    """Status of feedback."""
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


@strawberry.type
class FeedbackType:
    """User feedback for bug reports, feature requests, and improvements."""
    id: str
    userId: str
    type: FeedbackTypeEnum
    description: str
    rating: int = strawberry.field(description="Rating from 1-5 stars")
    status: FeedbackStatusEnum
    createdAt: datetime
    updatedAt: Optional[datetime]
