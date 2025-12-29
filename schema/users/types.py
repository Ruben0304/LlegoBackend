"""GraphQL type definitions for User entity."""
import strawberry
from datetime import datetime
from typing import Optional, List

from utils.s3 import generate_presigned_url


@strawberry.type
class UserType:
    id: str
    name: str
    email: str
    phone: Optional[str]
    role: str
    avatar: Optional[str]
    businessIds: List[str]
    branchIds: List[str]
    createdAt: datetime
    authProvider: str
    providerUserId: Optional[str]
    applePrivateEmail: Optional[str]

    @strawberry.field(description="URL firmada del avatar del usuario")
    def avatar_url(self) -> Optional[str]:
        """Generate presigned URL for user avatar."""
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None
