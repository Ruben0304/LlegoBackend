"""App configuration repository for database operations."""
from typing import Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import AppConfig


class AppConfigRepository:
    collection_name = "app_config"

    async def get(self) -> Optional[AppConfig]:
        """Get the app configuration (assumes single document in collection)."""
        db = get_database()
        config = await db[self.collection_name].find_one()
        return AppConfig(**self._convert_id(config)) if config else None

    async def get_by_id(self, config_id: str) -> Optional[AppConfig]:
        """Get app configuration by ID."""
        db = get_database()
        try:
            object_id = ObjectId(config_id)
        except Exception:
            object_id = config_id
        config = await db[self.collection_name].find_one({"_id": object_id})
        return AppConfig(**self._convert_id(config)) if config else None

    async def update(self, config_id: str, updates: Dict[str, Any]) -> Optional[AppConfig]:
        """Update app configuration in MongoDB."""
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
        return AppConfig(**self._convert_id(result)) if result else None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
