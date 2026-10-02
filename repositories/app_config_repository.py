"""App configuration repository for database operations with Redis caching."""
from typing import Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from datetime import datetime

from domain.models import AppConfig, BusinessAppConfig, CourierAppConfig
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


def default_courier_app_config_doc() -> Dict[str, Any]:
    """Configuración inicial de la app de choferes: sin versión mínima (no
    bloquea a nadie) y sin mantenimiento. La crea la primera
    `updateCourierAppConfig`, porque la colección nace vacía."""
    return {
        "android": {
            "minVersion": "0.0.0",
            "currentVersion": "0.0.0",
            "updateUrl": "",
            "storeUrl": "",
            "appSize": "",
        },
        "ios": {"minVersion": "0.0.0", "currentVersion": "0.0.0", "storeUrl": ""},
        "maintenance": {"enabled": False, "message": None},
        "updateMessage": None,
        "changelog": None,
        "releaseDate": datetime.utcnow(),
    }


class CourierAppConfigRepository:
    """Configuración de la app de choferes (AppMensajeros), cacheada en Redis
    igual que la de clientes y negocios."""
    collection_name = "courier_app_config"
    cache_key = "cache:courier_app_config"

    async def get(self) -> Optional[CourierAppConfig]:
        """Config desde la caché de Redis; si falla, desde MongoDB."""
        cached = get_cached(self.cache_key)
        if cached:
            return CourierAppConfig(**cached)

        db = get_database()
        config = await db[self.collection_name].find_one()
        if config:
            config_obj = CourierAppConfig(**self._convert_id(config))
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj
        return None

    async def get_or_create(self) -> CourierAppConfig:
        """Config actual, creando la inicial si la colección está vacía."""
        current = await self.get()
        if current:
            return current
        db = get_database()
        doc = default_courier_app_config_doc()
        result = await db[self.collection_name].insert_one(doc)
        doc["_id"] = result.inserted_id
        config_obj = CourierAppConfig(**self._convert_id(doc))
        invalidate_cache(self.cache_key)
        set_cached(self.cache_key, config_obj.model_dump())
        return config_obj

    async def update(self, config_id: str, updates: Dict[str, Any]) -> Optional[CourierAppConfig]:
        """Actualiza MongoDB y refresca la caché de Redis."""
        db = get_database()
        try:
            object_id = ObjectId(config_id)
        except Exception:
            object_id = config_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        if result:
            config_obj = CourierAppConfig(**self._convert_id(result))
            invalidate_cache(self.cache_key)
            set_cached(self.cache_key, config_obj.model_dump())
            return config_obj
        return None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
