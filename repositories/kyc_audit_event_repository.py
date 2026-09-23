"""Append-only audit repository for KYC actions."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.kyc import KycAuditEvent


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

    async def list_by_entity(
        self,
        entity_id: str,
        entity_type: str = "kyc_verification",
    ) -> List[KycAuditEvent]:
        """Audit trail for one entity, oldest first (chronological)."""
        cursor = self._collection().find(
            {"entityType": entity_type, "entityId": entity_id}
        ).sort("createdAt", 1)
        events = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            events.append(KycAuditEvent(**doc))
        return events


kyc_audit_events_repo = KycAuditEventRepository()
