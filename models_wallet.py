"""Wallet transaction models for the wallet system."""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal


class WalletTransaction(BaseModel):
    """Transaction record for wallet operations."""
    id: str = Field(alias="_id")
    fromOwnerId: Optional[str] = None  # None for external deposits
    fromOwnerType: Optional[Literal["user", "business"]] = None
    toOwnerId: Optional[str] = None  # None for withdrawals
    toOwnerType: Optional[Literal["user", "business"]] = None
    amount: Decimal
    currency: Literal["local", "usd"]
    type: Literal["transfer", "deposit", "withdrawal"]
    status: Literal["pending", "completed", "failed", "reversed"] = "completed"
    description: Optional[str] = None
    metadata: Optional[dict] = None  # Additional info (order_id, payment_gateway_id, etc)
    createdAt: datetime
    completedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }


class WalletBalance(BaseModel):
    """Wallet balance response model."""
    local: Decimal = Field(default=Decimal("0.00"))
    usd: Decimal = Field(default=Decimal("0.00"))

    class Config:
        json_encoders = {Decimal: lambda v: float(v)}
