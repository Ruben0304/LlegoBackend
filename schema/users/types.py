"""GraphQL type definitions for User entity."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import strawberry
from strawberry.scalars import JSON

from schema.wallet.types import WalletBalanceType
from utils.s3 import get_public_url


@strawberry.type
class SavedAddressType:
    """A saved delivery address in the user's profile."""

    id: str
    label: str
    street: str
    city: Optional[str]
    reference: Optional[str]
    addressType: str
    buildingName: Optional[str]
    floor: Optional[str]
    apartment: Optional[str]
    deliveryInstructions: Optional[str]
    latitude: float
    longitude: float


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
    location: Optional[JSON] = (
        None  # GeoJSON: {"type": "Point", "coordinates": [lon, lat]}
    )
    aiConsultasLimit: Optional[JSON] = None
    # Saved delivery addresses (Uber Eats / Glovo style)
    savedAddresses: List[SavedAddressType] = strawberry.field(default_factory=list)
    defaultAddressId: Optional[str] = None
    deliveredOrdersCount: int = 0
    scheduledDeletionAt: Optional[datetime] = None

    @strawberry.field(description="URL firmada del avatar del usuario")
    def avatar_url(self) -> Optional[str]:
        """Generate presigned URL for user avatar."""
        if self.avatar:
            return get_public_url(self.avatar)
        return None
