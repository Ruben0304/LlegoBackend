"""GraphQL type definitions for Wallet."""
import strawberry
from datetime import datetime
from typing import Optional


@strawberry.type
class WalletBalanceType:
    """Wallet balance for a user or business."""
    local: float
    usd: float


@strawberry.type
class WalletStatusType:
    """Wallet status information."""
    balance: WalletBalanceType
    status: str  # "active", "frozen", "closed"


@strawberry.type
class WalletTransactionType:
    """Wallet transaction record."""
    id: str
    from_owner_id: Optional[str]
    from_owner_type: Optional[str]
    to_owner_id: Optional[str]
    to_owner_type: Optional[str]
    amount: float
    currency: str
    type: str  # "transfer", "deposit", "withdrawal"
    status: str  # "pending", "completed", "failed", "reversed"
    description: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
