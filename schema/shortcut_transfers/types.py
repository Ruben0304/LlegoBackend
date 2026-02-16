"""GraphQL type definitions for ShortcutTransfer entity."""

from datetime import datetime
from typing import Optional

import strawberry


@strawberry.type
class ShortcutTransferType:
    """A bank transfer registered via iOS Shortcuts."""

    id: str = strawberry.field(description="Transfer record ID")
    transfer_id: str = strawberry.field(description="Bank transfer ID from SMS")
    amount: float = strawberry.field(description="Transfer amount")
    phone: Optional[str] = strawberry.field(
        description="Phone that received the SMS", default=None
    )
    date: Optional[datetime] = strawberry.field(
        description="Transfer date from SMS", default=None
    )
    activated: bool = strawberry.field(
        description="Whether this transfer has been used"
    )
    activated_at: Optional[datetime] = strawberry.field(
        description="When it was activated", default=None
    )
    created_at: datetime = strawberry.field(description="When the record was created")


def shortcut_transfer_to_type(transfer) -> ShortcutTransferType:
    """Convert ShortcutTransfer domain model to GraphQL type."""
    return ShortcutTransferType(
        id=transfer.id,
        transfer_id=transfer.transfer_id,
        amount=transfer.amount,
        phone=transfer.phone,
        date=transfer.date,
        activated=transfer.activated,
        activated_at=transfer.activated_at,
        created_at=transfer.created_at,
    )
