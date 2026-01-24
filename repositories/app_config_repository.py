"""App configuration repository for database operations with Redis caching."""
from typing import Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import AppConfig, BusinessAppConfig
from utils.cache import get_cached, set_cached, invalidate_cache


class AppConfigRepository:
    """Repository for customer app configuration with Redis caching."""
    collection_name = "app_config"
    cache_key = "cache:app_config"

    async def get(self) -> Optional[AppConfig]:
        """
        Get the customer app configuration from Redis cache.
        Falls back to MongoDB if cache miss.
        """
        # Try cache first
        cached = get_cached(self.cache_key)
        if cached:
            return AppConfig(**cached)

        # Cache miss - fetch from MongoDB
        db = get_database()
        config = await db[self.collection_name].find_one()

        if config:
            config_obj = AppConfig(**self._convert_id(config))
            # Cache the result (no TTL - permanent cache)
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj

        return None

    async def get_by_id(self, config_id: str) -> Optional[AppConfig]:
        """Get app configuration by ID (uses cache)."""
        # Use the same cache key since there's only one config
        return await self.get()

    async def update(self, config_id: str, updates: Dict[str, Any]) -> Optional[AppConfig]:
        """
        Update app configuration in MongoDB and refresh Redis cache.
        """
        db = get_database()
        try:
            object_id = ObjectId(config_id)
        except Exception:
            object_id = config_id

        # Update in MongoDB
        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )

        if result:
            config_obj = AppConfig(**self._convert_id(result))
            # Invalidate and refresh cache
            invalidate_cache(self.cache_key)
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj

        return None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc


class BusinessAppConfigRepository:
    """Repository for business/merchant app configuration with Redis caching."""
    collection_name = "business_app_config"
    cache_key = "cache:business_app_config"

    async def get(self) -> Optional[BusinessAppConfig]:
        """
        Get the business app configuration from Redis cache.
        Falls back to MongoDB if cache miss.
        """
        # Try cache first
        cached = get_cached(self.cache_key)
        if cached:
            return BusinessAppConfig(**cached)

        # Cache miss - fetch from MongoDB
        db = get_database()
        config = await db[self.collection_name].find_one()

        if config:
            config_obj = BusinessAppConfig(**self._convert_id(config))
            # Cache the result (no TTL - permanent cache)
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj

        return None

    async def get_by_id(self, config_id: str) -> Optional[BusinessAppConfig]:
        """Get business app configuration by ID (uses cache)."""
        # Use the same cache key since there's only one config
        return await self.get()

    async def update(self, config_id: str, updates: Dict[str, Any]) -> Optional[BusinessAppConfig]:
        """
        Update business app configuration in MongoDB and refresh Redis cache.
        """
        db = get_database()
        try:
            object_id = ObjectId(config_id)
        except Exception:
            object_id = config_id

        # Update in MongoDB
        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )

        if result:
            config_obj = BusinessAppConfig(**self._convert_id(result))
            # Invalidate and refresh cache
            invalidate_cache(self.cache_key)
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj

        return None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
