"""Append-only audit repository for KYC actions."""

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from clients import get_database


class KycAuditEventRepository:
    collection_name = "kyc_audit_events"

    def _collection(self):
        return get_database()[self.collection_name]

    async def append(
        self,
        *,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_type: str,
        actor_id: Optional[str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        doc = {
            "_id": ObjectId(),
            "entityType": entity_type,
            "entityId": entity_id,
            "eventType": event_type,
            "actorType": actor_type,
            "actorId": actor_id,
            "payload": payload or {},
            "createdAt": datetime.utcnow(),
        }
        await self._collection().insert_one(doc)
        return str(doc["_id"])


kyc_audit_events_repo = KycAuditEventRepository()
