"""Repositorio de los banners de plataforma (`platform_banners`)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.platform_banners import PlatformBanner


def active_banners_filter(app_target: str, now: datetime) -> Dict[str, Any]:
    """Filtro Mongo de los banners visibles ahora en una app.

    Activo y dentro de su ventana opcional [startAt, endAt). Un banner sin
    fechas se muestra mientras esté activo.
    """
    return {
        "appTarget": app_target,
        "isActive": True,
        "$and": [
            {"$or": [{"startAt": None}, {"startAt": {"$lte": now}}]},
            {"$or": [{"endAt": None}, {"endAt": {"$gt": now}}]},
        ],
    }


class PlatformBannerRepository:
    collection_name = "platform_banners"

    @staticmethod
    def _object_id(value: Optional[str]):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    @staticmethod
    def _to_model(doc: Dict[str, Any]) -> PlatformBanner:
        doc["_id"] = str(doc["_id"])
        return PlatformBanner(**doc)

    async def get_active(self, app_target: str, now: Optional[datetime] = None) -> List[PlatformBanner]:
        """Banners visibles ahora para `app_target`, en el orden del carrusel."""
        db = get_database()
        cursor = (
            db[self.collection_name]
            .find(active_banners_filter(app_target, now or datetime.utcnow()))
            .sort([("order", 1), ("createdAt", 1)])
        )
        docs = await cursor.to_list(length=None)
        return [self._to_model(d) for d in docs]

    async def list_all(self, app_target: Optional[str] = None) -> List[PlatformBanner]:
        """Todos los banners (activos o no) para el panel admin."""
        db = get_database()
        query: Dict[str, Any] = {"appTarget": app_target} if app_target else {}
        cursor = db[self.collection_name].find(query).sort([("order", 1), ("createdAt", 1)])
        docs = await cursor.to_list(length=None)
        return [self._to_model(d) for d in docs]

    async def get_by_id(self, banner_id: str) -> Optional[PlatformBanner]:
        db = get_database()
        doc = await db[self.collection_name].find_one({"_id": self._object_id(banner_id)})
        return self._to_model(doc) if doc else None

    async def next_order(self, app_target: str) -> int:
        """Posición al final del carrusel de esa app."""
        db = get_database()
        last = await db[self.collection_name].find_one(
            {"appTarget": app_target}, sort=[("order", -1)]
        )
        return int(last.get("order", 0)) + 1 if last else 0

    async def create(self, data: Dict[str, Any]) -> PlatformBanner:
        db = get_database()
        now = datetime.utcnow()
        doc = {**data, "createdAt": now, "updatedAt": None}
        for key in ("branchId", "createdByUserId"):
            if doc.get(key):
                doc[key] = self._object_id(doc[key])
        result = await db[self.collection_name].insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._to_model(doc)

    async def update(self, banner_id: str, updates: Dict[str, Any]) -> Optional[PlatformBanner]:
        db = get_database()
        updates = {**updates, "updatedAt": datetime.utcnow()}
        if updates.get("branchId"):
            updates["branchId"] = self._object_id(updates["branchId"])
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": self._object_id(banner_id)},
            {"$set": updates},
            return_document=True,
        )
        return self._to_model(doc) if doc else None

    async def delete(self, banner_id: str) -> bool:
        db = get_database()
        result = await db[self.collection_name].delete_one({"_id": self._object_id(banner_id)})
        return result.deleted_count > 0

    async def reorder(self, banner_ids: List[str]) -> None:
        """Fija `order` = posición en la lista recibida."""
        db = get_database()
        now = datetime.utcnow()
        for position, banner_id in enumerate(banner_ids):
            await db[self.collection_name].update_one(
                {"_id": self._object_id(banner_id)},
                {"$set": {"order": position, "updatedAt": now}},
            )


platform_banners_repo = PlatformBannerRepository()
