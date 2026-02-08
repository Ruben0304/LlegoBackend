"""Platform module for system-level configuration and wallet."""

from .models import Platform, PlatformWallet, QrPayment, TransferAccount, TransferPhone
from .repository import PlatformRepository

platform_repo = PlatformRepository()

__all__ = [
    "Platform",
    "PlatformWallet",
    "TransferAccount",
    "QrPayment",
    "TransferPhone",
    "PlatformRepository",
    "platform_repo",
]
