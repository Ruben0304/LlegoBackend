"""Service for shortcut transfer business logic."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from domain.shortcut_transfer import ShortcutTransfer
from repositories.shortcut_transfer_repository import ShortcutTransferRepository


class ShortcutTransferService:
    """Business logic for shortcut transfers."""

    def __init__(self):
        self.repo = ShortcutTransferRepository()

    async def register_transfer(
        self,
        transfer_id: str,
        amount: float,
        phone: Optional[str] = None,
        date: Optional[datetime] = None,
    ) -> ShortcutTransfer:
        """Register a new bank transfer from iOS Shortcuts."""
        transfer = ShortcutTransfer(
            _id=str(ObjectId()),
            transfer_id=transfer_id,
            amount=amount,
            phone=phone,
            date=date,
            activated=False,
            created_at=datetime.utcnow(),
        )
        return await self.repo.create(transfer)

    async def find_pending_transfer(
        self,
        transfer_id: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> List[ShortcutTransfer]:
        """Find pending (non-activated) transfers by transfer_id and/or phone."""
        if not transfer_id and not phone:
            raise ValueError("Debe proporcionar al menos transfer_id o phone")
        return await self.repo.find_pending(transfer_id=transfer_id, phone=phone)

    async def activate_transfer(self, id: str) -> Optional[ShortcutTransfer]:
        """Mark a transfer as activated."""
        return await self.repo.activate(id)


shortcut_transfer_service = ShortcutTransferService()
