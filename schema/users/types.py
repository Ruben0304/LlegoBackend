"""GraphQL type definitions for User entity."""
import strawberry
from datetime import datetime
from typing import Optional


@strawberry.type
class UserType:
    id: str
    name: str
    email: str
    phone: Optional[str]
    role: str
    createdAt: datetime
    authProvider: str
    providerUserId: Optional[str]
    applePrivateEmail: Optional[str]
