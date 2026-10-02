"""Repositorio de `partner_requests` (registro de socios: negocios y mensajeros)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.partner_requests import (
    PartnerRequest,
    PartnerRequestKind,
    PartnerRequestStatus,
    is_active_status,
)


class PartnerRequestRepository:
    """Persistencia de las solicitudes para vender en Llegó o ser mensajero.

    La unicidad "una solicitud activa por usuario y tipo" la garantiza el índice
    único parcial sobre `active` (clients/mongodb_client.py): `create` y
    `update_status` pueden lanzar `DuplicateKeyError` y el servicio lo traduce a un
    mensaje claro.
    """

    collection_name = "partner_requests"

    def _collection(self):
        return get_database()[self.collection_name]

    async def create(self, data: Dict[str, Any]) -> PartnerRequest:
        """Guarda una solicitud nueva en estado `pending`."""
        now = datetime.now(timezone.utc)
        doc = {
            **data,
            "userId": self._object_id(data["userId"]),
            "type": PartnerRequestKind(data["type"]).value,
            "status": PartnerRequestStatus.PENDING.value,
            "active": True,
            "adminNotes": None,
            "reviewedAt": None,
            "reviewedBy": None,
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self._collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._to_model(doc)

    async def get_by_id(self, request_id: str) -> Optional[PartnerRequest]:
        doc = await self._collection().find_one({"_id": self._object_id(request_id)})
        return self._to_model(doc) if doc else None

    async def get_active_for_user(
        self, user_id: str, kind: PartnerRequestKind
    ) -> Optional[PartnerRequest]:
        """Solicitud pendiente o contactada del usuario para ese tipo, si la hay."""
        doc = await self._collection().find_one(
            {
                "userId": self._object_id(user_id),
                "type": PartnerRequestKind(kind).value,
                "active": True,
            }
        )
        return self._to_model(doc) if doc else None

    async def get_latest_for_user(
        self, user_id: str, kind: PartnerRequestKind
    ) -> Optional[PartnerRequest]:
        """La solicitud más reciente del usuario para ese tipo, en cualquier estado."""
        doc = await self._collection().find_one(
            {
                "userId": self._object_id(user_id),
                "type": PartnerRequestKind(kind).value,
            },
            sort=[("createdAt", -1)],
        )
        return self._to_model(doc) if doc else None

    async def exists_with_status(
        self, user_id: str, kind: PartnerRequestKind, status: PartnerRequestStatus
    ) -> bool:
        """Si el usuario tiene alguna solicitud de ese tipo en ese estado."""
        doc = await self._collection().find_one(
            {
                "userId": self._object_id(user_id),
                "type": PartnerRequestKind(kind).value,
                "status": PartnerRequestStatus(status).value,
            },
            {"_id": 1},
        )
        return doc is not None

    async def list_requests(
        self,
        status: Optional[PartnerRequestStatus] = None,
        kind: Optional[PartnerRequestKind] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[PartnerRequest]:
        """Solicitudes de la más nueva a la más antigua, con filtros opcionales."""
        cursor = (
            self._collection()
            .find(self._filter(status, kind))
            .sort("createdAt", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._to_model(d) for d in docs]

    async def count_requests(
        self,
        status: Optional[PartnerRequestStatus] = None,
        kind: Optional[PartnerRequestKind] = None,
    ) -> int:
        return await self._collection().count_documents(self._filter(status, kind))

    async def update_status(
        self,
        request_id: str,
        status: PartnerRequestStatus,
        reviewed_by: str,
        expected_status: PartnerRequestStatus,
        admin_notes: Optional[str] = None,
        update_admin_notes: bool = False,
    ) -> Optional[PartnerRequest]:
        """Cambia el estado desde el Panel Admin y registra quién y cuándo.

        Solo se aplica si la solicitud sigue en `expected_status` (el estado que
        leyó el servicio): si otro admin la cambió entretanto devuelve None en vez
        de pisar su decisión. `active` se recalcula con el estado. Con
        `update_admin_notes` también se sobrescriben las notas internas (None las
        borra).
        """
        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "status": PartnerRequestStatus(status).value,
            "active": is_active_status(status),
            "reviewedAt": now,
            "reviewedBy": self._object_id(reviewed_by),
            "updatedAt": now,
        }
        if update_admin_notes:
            updates["adminNotes"] = admin_notes

        doc = await self._collection().find_one_and_update(
            {
                "_id": self._object_id(request_id),
                "status": PartnerRequestStatus(expected_status).value,
            },
            {"$set": updates},
            return_document=True,
        )
        return self._to_model(doc) if doc else None

    @staticmethod
    def _filter(
        status: Optional[PartnerRequestStatus], kind: Optional[PartnerRequestKind]
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if status is not None:
            query["status"] = PartnerRequestStatus(status).value
        if kind is not None:
            query["type"] = PartnerRequestKind(kind).value
        return query

    @staticmethod
    def _object_id(value: Any) -> Any:
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    @staticmethod
    def _to_model(doc: Dict[str, Any]) -> PartnerRequest:
        doc = dict(doc)
        doc["_id"] = str(doc["_id"])
        # Mongo devuelve las fechas sin zona (UTC). Se marcan como UTC para que
        # GraphQL las emita con "+00:00": la web las pasa a `new Date()`, que
        # tomaría una fecha sin zona como hora local.
        for key in ("createdAt", "updatedAt", "reviewedAt"):
            value = doc.get(key)
            if isinstance(value, datetime) and value.tzinfo is None:
                doc[key] = value.replace(tzinfo=timezone.utc)
        return PartnerRequest(**doc)
