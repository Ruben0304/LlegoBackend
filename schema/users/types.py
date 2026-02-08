"""GraphQL type definitions for User entity."""
import strawberry
from datetime import datetime
from typing import Optional, List, Dict

from utils.s3 import generate_presigned_url
from schema.wallet.types import WalletBalanceType


@strawberry.type
class UserType:
    id: str
    name: str
    email: str
    username: str
    phone: Optional[str]
    role: str
    avatar: Optional[str]
    businessIds: List[str]
    branchIds: List[str]
    businessAccessIds: List[str]
    createdAt: datetime
    authProvider: str
    providerUserId: Optional[str]
    applePrivateEmail: Optional[str]
    wallet: WalletBalanceType
    walletStatus: str = "active"
    isPro: bool = False

    @strawberry.field(description="URL firmada del avatar del usuario")
    def avatar_url(self) -> Optional[str]:
        """Generate presigned URL for user avatar."""
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None
