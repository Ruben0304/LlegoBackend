"""Platform module for system-level configuration and wallet."""
from .models import Platform, PlatformWallet
from .repository import PlatformRepository

platform_repo = PlatformRepository()

__all__ = [
    "Platform",
    "PlatformWallet",
    "PlatformRepository",
    "platform_repo",
]
