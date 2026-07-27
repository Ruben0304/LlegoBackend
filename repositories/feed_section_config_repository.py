"""Feed section ordering configuration repository."""
from typing import Dict

from clients import get_database
from utils.cache import mem_cache

_CACHE_KEY = "feed:section_orden_map"
_CACHE_TTL = 60


class FeedSectionConfigRepository:
    """Persisted position overrides for feed sections."""

    collection_name = "feed_section_config"

    async def get_orden_map(self) -> Dict[str, int]:
        """Return {section_id: orden} for the sections pinned to a fixed position."""
        cached = mem_cache.get(_CACHE_KEY)
        if cached is not None:
            return cached

        db = get_database()
        cursor = db[self.collection_name].find({"orden": {"$ne": None}})
        docs = await cursor.to_list(length=None)
        orden_map = {
            doc["sectionId"]: doc["orden"] for doc in docs if doc.get("sectionId")
        }
        mem_cache.set(_CACHE_KEY, orden_map, ttl=_CACHE_TTL)
        return orden_map

    async def set_orden(self, section_id: str, orden: int) -> None:
        """Pin a section to a fixed position at the top of the feed."""
        db = get_database()
        await db[self.collection_name].update_one(
            {"sectionId": section_id},
            {"$set": {"sectionId": section_id, "orden": orden}},
            upsert=True,
        )
        mem_cache.invalidate(_CACHE_KEY)

    async def clear_orden(self, section_id: str) -> None:
        """Remove the pinned position so the section falls back to its default spot."""
        db = get_database()
        await db[self.collection_name].delete_one({"sectionId": section_id})
        mem_cache.invalidate(_CACHE_KEY)
