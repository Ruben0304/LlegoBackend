"""Repository for shortcut transfer operations."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.shortcut_transfer import ShortcutTransfer
from utils.phone import cuban_national_number, cuban_phone_variants


class ShortcutTransferRepository:
    """Repository for shortcut transfer CRUD operations."""

    collection_name = "shortcut_transfers"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _doc_to_model(doc: dict) -> ShortcutTransfer:
        """Convert MongoDB document to ShortcutTransfer model."""
        doc["_id"] = str(doc["_id"])
        return ShortcutTransfer(**doc)

    async def create(self, transfer: ShortcutTransfer) -> ShortcutTransfer:
        """Create a new shortcut transfer record."""
        collection = self._get_collection()
        doc = transfer.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return transfer

    async def find_pending(
        self,
        transfer_id: Optional[str] = None,
        phone: Optional[str] = None,
        created_after: Optional[datetime] = None,
    ) -> List[ShortcutTransfer]:
        """Find pending (non-activated) transfers by transfer_id and/or phone."""
        query = build_pending_transfers_query(transfer_id, phone, created_after)
        collection = self._get_collection()
        cursor = collection.find(query).sort("created_at", -1)
        return [self._doc_to_model(doc) async for doc in cursor]

    async def activate(self, transfer_id: str) -> Optional[ShortcutTransfer]:
        """Mark a pending transfer as activated.

        Compare-and-set sobre `activated: False`: si dos confirmaciones compiten por la
        misma transferencia solo una la obtiene; la otra recibe None.
        """
        collection = self._get_collection()
        now = datetime.utcnow()
        update = {"$set": {"activated": True, "activated_at": now}}
        try:
            doc = await collection.find_one_and_update(
                {"_id": ObjectId(transfer_id), "activated": False},
                update,
                return_document=True,
            )
        except Exception:
            doc = await collection.find_one_and_update(
                {"_id": transfer_id, "activated": False},
                update,
                return_document=True,
            )
        return self._doc_to_model(doc) if doc else None


def build_pending_transfers_query(
    transfer_id: Optional[str] = None,
    phone: Optional[str] = None,
    created_after: Optional[datetime] = None,
) -> dict:
    """Query de transferencias pendientes; el teléfono se compara sin depender del formato."""
    query: dict = {"activated": False}
    if transfer_id:
        query["transfer_id"] = transfer_id
    if phone:
        national = cuban_national_number(phone)
        if national:
            # Registros nuevos traen phone_national; los antiguos solo `phone` en su formato.
            query["$or"] = [
                {"phone_national": national},
                {"phone": {"$in": cuban_phone_variants(phone)}},
            ]
        else:
            query["phone"] = phone.strip()
    if created_after:
        query["created_at"] = {"$gte": created_after}
    return query


shortcut_transfers_repo = ShortcutTransferRepository()
