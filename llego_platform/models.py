"""Platform models for system-level configuration and wallet."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PlatformWallet(BaseModel):
    """Platform wallet balance."""

    local: float = 0.0  # CUP
    usd: float = 0.0


class TransferAccount(BaseModel):
    """Bank card account for CUP transfers."""

    cardNumber: str
    cardHolderName: str
    bankName: str
    isActive: bool = True


class QrPayment(BaseModel):
    """QR payment info for online payments (EnZona, etc.)."""

    value: str
    isActive: bool = True


class TransferPhone(BaseModel):
    """Phone number for mobile transfers (Transfermóvil, etc.)."""

    phone: str
    isActive: bool = True


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

    # Transfer payment info (CUP)
    accounts: List[TransferAccount] = Field(default_factory=list)
    qrPayments: List[QrPayment] = Field(default_factory=list)
    phones: List[TransferPhone] = Field(default_factory=list)

    # Statistics
    totalCommissionsCollected: float = 0.0
    totalOrdersProcessed: int = 0

    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}
