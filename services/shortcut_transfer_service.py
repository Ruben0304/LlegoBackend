"""Service for shortcut transfer business logic."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from domain.shortcut_transfer import ShortcutTransfer
from repositories.shortcut_transfer_repository import ShortcutTransferRepository
from utils.phone import cuban_national_number

# Margen para errores de redondeo al comparar montos (CUP con 2 decimales).
AMOUNT_TOLERANCE = 0.01


def transfers_covering_amount(
    transfers: List[ShortcutTransfer], amount: float
) -> List[ShortcutTransfer]:
    """Transferencias cuyo monto cubre `amount`, la más ajustada primero.

    Nunca se acepta una transferencia por menos del total. Entre las que cubren, se
    prefiere la de monto más cercano (y la más reciente ante empate) para no consumir
    una transferencia mayor que probablemente pertenece a otro pedido.
    """
    covering = [t for t in transfers if t.amount + AMOUNT_TOLERANCE >= amount]
    return sorted(covering, key=lambda t: (t.amount, -t.created_at.timestamp()))


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
            phone_national=cuban_national_number(phone),
            date=date,
            activated=False,
            created_at=datetime.utcnow(),
        )
        return await self.repo.create(transfer)

    async def find_pending_transfer(
        self,
        transfer_id: Optional[str] = None,
        phone: Optional[str] = None,
        created_after: Optional[datetime] = None,
    ) -> List[ShortcutTransfer]:
        """Find pending (non-activated) transfers by transfer_id and/or phone."""
        if not transfer_id and not phone:
            raise ValueError("Debe proporcionar al menos transfer_id o phone")
        return await self.repo.find_pending(
            transfer_id=transfer_id, phone=phone, created_after=created_after
        )

    async def activate_transfer(self, id: str) -> Optional[ShortcutTransfer]:
        """Mark a transfer as activated. None si otra confirmación ya la usó."""
        return await self.repo.activate(id)


shortcut_transfer_service = ShortcutTransferService()
