"""Platform models for system-level configuration and wallet."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PlatformWallet(BaseModel):
    """Platform wallet balance."""
    local: float = 0.0  # CUP
    usd: float = 0.0


class Platform(BaseModel):
    """
    Platform entity - stores system-level configuration and the platform wallet
    where commissions are collected.

    This is a singleton document in the database.
    """
    id: str = Field(alias="_id", default="platform")

    # Platform info
    name: str = "Llego"

    # Wallet for collecting commissions
    wallet: PlatformWallet = Field(default_factory=PlatformWallet)
    walletStatus: str = "active"  # "active", "frozen"

    # Statistics
    totalCommissionsCollected: float = 0.0
    totalOrdersProcessed: int = 0

    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}
