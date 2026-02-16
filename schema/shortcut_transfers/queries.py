"""GraphQL query resolvers for ShortcutTransfer."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from schema.shortcut_transfers.types import (
    ShortcutTransferType,
    shortcut_transfer_to_type,
)
from services.shortcut_transfer_service import shortcut_transfer_service
from utils.graphql_auth import require_auth


@strawberry.type
class ShortcutTransferQuery:
    @strawberry.field(
        description="Buscar transferencias pendientes por transfer_id y/o teléfono"
    )
    async def find_pending_transfers(
        self,
        info: Info,
        jwt: str,
        transfer_id: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> List[ShortcutTransferType]:
        """
        Find pending (non-activated) transfers by transfer_id and/or phone.

        At least one of transfer_id or phone must be provided.
        Requires JWT authentication.

        Args:
            jwt: User JWT token
            transfer_id: Bank transfer ID to search for
            phone: Phone number to search for

        Returns:
            List of matching pending transfers
        """
        require_auth(jwt, info)

        try:
            transfers = await shortcut_transfer_service.find_pending_transfer(
                transfer_id=transfer_id,
                phone=phone,
            )
            return [shortcut_transfer_to_type(t) for t in transfers]
        except ValueError as e:
            raise Exception(str(e))
