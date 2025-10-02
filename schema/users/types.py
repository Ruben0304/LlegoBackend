"""GraphQL type definitions for User entity."""
import strawberry
from datetime import datetime


@strawberry.type
class UserType:
    id: str
    name: str
    email: str
    role: str
    createdAt: datetime
