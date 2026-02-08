"""Repository for delivery zone operations using H3 hexagonal zones."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.models import DeliveryZone


class DeliveryZoneRepository:
    """Repository for delivery zone database operations."""

    collection_name = "delivery_zones"

    def _get_collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def _doc_to_zone(doc: dict) -> DeliveryZone:
        """Convert MongoDB document to DeliveryZone model."""
        doc["_id"] = str(doc["_id"])
        return DeliveryZone(**doc)

    async def get_all(self, active_only: bool = True) -> List[DeliveryZone]:
        """Get all delivery zones."""
        collection = self._get_collection()
        query = {"isActive": True} if active_only else {}
        cursor = collection.find(query)
        documents = await cursor.to_list(length=None)
        return [self._doc_to_zone(doc) for doc in documents]

    async def get_by_id(self, zone_id: str) -> Optional[DeliveryZone]:
        """Get a delivery zone by its ID."""
        collection = self._get_collection()
        doc = await collection.find_one({"_id": ObjectId(zone_id)})
        return self._doc_to_zone(doc) if doc else None

    async def get_by_h3_index(self, h3_index: str) -> Optional[DeliveryZone]:
        """Get a delivery zone by its H3 index."""
        collection = self._get_collection()
        doc = await collection.find_one({"h3Index": h3_index, "isActive": True})
        return self._doc_to_zone(doc) if doc else None

    async def get_by_h3_indexes(self, h3_indexes: List[str]) -> List[DeliveryZone]:
        """Get multiple delivery zones by their H3 indexes."""
        collection = self._get_collection()
        cursor = collection.find({"h3Index": {"$in": h3_indexes}, "isActive": True})
        documents = await cursor.to_list(length=None)
        return [self._doc_to_zone(doc) for doc in documents]

    async def get_by_city(self, city: str) -> List[DeliveryZone]:
        """Get all delivery zones for a city."""
        collection = self._get_collection()
        cursor = collection.find({"city": city, "isActive": True})
        documents = await cursor.to_list(length=None)
        return [self._doc_to_zone(doc) for doc in documents]

    async def get_by_province(self, province: str) -> List[DeliveryZone]:
        """Get all delivery zones for a province."""
        collection = self._get_collection()
        cursor = collection.find({"province": province, "isActive": True})
        documents = await cursor.to_list(length=None)
        return [self._doc_to_zone(doc) for doc in documents]

    async def create(self, zone: DeliveryZone) -> DeliveryZone:
        """Create a new delivery zone."""
        collection = self._get_collection()
        doc = zone.model_dump(by_alias=True)
        doc["_id"] = ObjectId(doc["_id"])
        await collection.insert_one(doc)
        return zone

    async def create_many(self, zones: List[DeliveryZone]) -> int:
        """Bulk create delivery zones. Returns count of inserted documents."""
        if not zones:
            return 0
        collection = self._get_collection()
        docs = []
        for zone in zones:
            doc = zone.model_dump(by_alias=True)
            doc["_id"] = ObjectId(doc["_id"])
            docs.append(doc)
        result = await collection.insert_many(docs)
        return len(result.inserted_ids)

    async def update(self, zone_id: str, updates: dict) -> Optional[DeliveryZone]:
        """Update a delivery zone by ID."""
        collection = self._get_collection()
        updates["updatedAt"] = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": ObjectId(zone_id)}, {"$set": updates}, return_document=True
        )
        return self._doc_to_zone(result) if result else None

    async def update_pricing(
        self,
        zone_id: str,
        base_fee: Optional[float] = None,
        per_km_fee: Optional[float] = None,
        surcharge_percent: Optional[float] = None,
        max_delivery_fee: Optional[float] = None,
    ) -> Optional[DeliveryZone]:
        """Update pricing fields for a delivery zone."""
        updates = {}
        if base_fee is not None:
            updates["baseFee"] = base_fee
        if per_km_fee is not None:
            updates["perKmFee"] = per_km_fee
        if surcharge_percent is not None:
            updates["surchargePercent"] = surcharge_percent
        if max_delivery_fee is not None:
            updates["maxDeliveryFee"] = max_delivery_fee
        if not updates:
            return await self.get_by_id(zone_id)
        return await self.update(zone_id, updates)

    async def activate(self, zone_id: str) -> Optional[DeliveryZone]:
        """Activate a delivery zone."""
        return await self.update(zone_id, {"isActive": True})

    async def deactivate(self, zone_id: str) -> Optional[DeliveryZone]:
        """Deactivate a delivery zone."""
        return await self.update(zone_id, {"isActive": False})

    async def delete(self, zone_id: str) -> bool:
        """Delete a delivery zone."""
        collection = self._get_collection()
        result = await collection.delete_one({"_id": ObjectId(zone_id)})
        return result.deleted_count > 0

    async def delete_by_city(self, city: str) -> int:
        """Delete all delivery zones for a city. Returns deleted count."""
        collection = self._get_collection()
        result = await collection.delete_many({"city": city})
        return result.deleted_count


async def create_delivery_zone_indexes():
    """Create MongoDB indexes for delivery_zones collection."""
    db = get_database()
    collection = db["delivery_zones"]

    # Unique index on h3Index — one zone per hexagon
    await collection.create_index(
        "h3Index",
        unique=True,
        name="idx_h3_index_unique",
        background=True,
    )

    # Lookup by city
    await collection.create_index(
        [("city", 1), ("isActive", 1)],
        name="idx_city_active",
        background=True,
    )

    # Lookup by province
    await collection.create_index(
        [("province", 1), ("isActive", 1)],
        name="idx_province_active",
        background=True,
    )

    # Active zones fast filter
    await collection.create_index(
        "isActive",
        name="idx_is_active",
        background=True,
    )

    print("✓ Delivery zone indexes created/verified")
