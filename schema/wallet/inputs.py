"""GraphQL input types for Wallet operations."""
import strawberry
from typing import Optional


@strawberry.input
class TransferInput:
    """Input for transferring money between wallets."""
    to_owner_id: Optional[str] = None  # User/Branch ID
    to_owner_email: Optional[str] = None  # User email (alternative to ID)
    to_owner_username: Optional[str] = None  # User username (alternative to ID)
    to_owner_type: str  # "user" or "branch"
    amount: float
    currency: str  # "local" or "usd"
    description: Optional[str] = None


@strawberry.input
class DepositInput:
    """Input for depositing money into wallet."""
    amount: float
    currency: str  # "local" or "usd"
    source: str  # "bank_transfer", "credit_card", etc.
    description: Optional[str] = None


@strawberry.input
class WithdrawInput:
    """Input for withdrawing money from wallet."""
    amount: float
    currency: str  # "local" or "usd"
    destination: str  # Bank account, card number, etc.
    description: Optional[str] = None
