"""Repository for the vehicles catalog collection."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.orders import Vehicle, VehicleType


class VehicleRepository:
    """CRUD for the vehicles catalog (triciclo, bicicleta, …)."""

    collection_name = "vehicles"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _doc_to_vehicle(doc: dict) -> Vehicle:
        doc["_id"] = str(doc["_id"])
        return Vehicle(**doc)

    async def get_all(self, active_only: bool = True) -> List[Vehicle]:
        """Return all vehicles, optionally filtering by isActive."""
        collection = self._get_collection()
        query = {"isActive": True} if active_only else {}
        cursor = collection.find(query).sort("name", 1)
        return [self._doc_to_vehicle(doc) async for doc in cursor]

    async def get_by_id(self, vehicle_id: str) -> Optional[Vehicle]:
        """Return a single vehicle by its MongoDB id."""
        collection = self._get_collection()
        try:
            oid = ObjectId(vehicle_id)
        except Exception:
            return None
        doc = await collection.find_one({"_id": oid})
        return self._doc_to_vehicle(doc) if doc else None

    async def get_by_slug(self, slug: str) -> Optional[Vehicle]:
        """Return a vehicle by its slug (e.g. 'bicicleta')."""
        collection = self._get_collection()
        doc = await collection.find_one({"slug": slug})
        return self._doc_to_vehicle(doc) if doc else None

    async def create(self, vehicle: Vehicle) -> Vehicle:
        """Insert a new vehicle document."""
        collection = self._get_collection()
        doc = vehicle.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"]) if doc.get("_id") else ObjectId()
        await collection.insert_one(doc)
        vehicle.id = str(doc["_id"])
        return vehicle

    async def upsert_seed(self, name: str, slug: VehicleType) -> Vehicle:
        """Insert the vehicle if a document with this slug does not already exist."""
        collection = self._get_collection()
        existing = await collection.find_one({"slug": slug.value})
        if existing:
            return self._doc_to_vehicle(existing)
        now = datetime.utcnow()
        doc = {
            "_id": ObjectId(),
            "name": name,
            "slug": slug.value,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
        }
        await collection.insert_one(doc)
        return self._doc_to_vehicle({**doc, "_id": str(doc["_id"])})


vehicles_repo = VehicleRepository()
