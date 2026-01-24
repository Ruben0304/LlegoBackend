"""GraphQL input types for Feedback mutations."""
import strawberry
from typing import Optional
from .types import FeedbackTypeEnum, FeedbackStatusEnum


@strawberry.input
class CreateFeedbackInput:
    """Input for creating feedback."""
    type: FeedbackTypeEnum
    description: str
    rating: int = strawberry.field(description="Rating from 1-5 stars")


@strawberry.input
class UpdateFeedbackStatusInput:
    """Input for updating feedback status (admin only)."""
    status: FeedbackStatusEnum
