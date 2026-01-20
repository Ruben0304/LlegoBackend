"""GraphQL type definitions for User entity."""
import strawberry
from datetime import datetime
from typing import Optional, List, Dict
from strawberry import Private

from utils.s3 import generate_presigned_url
from schema.wallet.types import WalletBalanceType


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

    # Private fields to store wallet data
    _wallet: Private[Optional[Dict[str, float]]] = None
    _wallet_status: Private[Optional[str]] = None

    @strawberry.field(description="Wallet balance del usuario")
    def wallet(self) -> WalletBalanceType:
        """Get wallet with default values if not exists."""
        if self._wallet:
            return WalletBalanceType(
                local=self._wallet.get('local', 0.0),
                usd=self._wallet.get('usd', 0.0)
            )
        # Si el usuario no tiene wallet, retornar valores por defecto
        return WalletBalanceType(local=0.0, usd=0.0)

    @strawberry.field(description="Estado de la wallet")
    def wallet_status(self) -> str:
        """Get wallet status with default value if not exists."""
        return self._wallet_status if self._wallet_status else "active"

    @strawberry.field(description="URL firmada del avatar del usuario")
    def avatar_url(self) -> Optional[str]:
        """Generate presigned URL for user avatar."""
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None
