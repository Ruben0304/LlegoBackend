"""GraphQL type definitions for Business entity."""
import strawberry
from datetime import datetime


@strawberry.type
class BusinessType:
    id: str
    name: str
    type: str
    ownerId: str
    globalRating: float
    createdAt: datetime
