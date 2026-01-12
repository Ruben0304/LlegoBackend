"""Business type configuration repository for database operations."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from clients import get_database
from models_business_types import BusinessTypeConfig


class BusinessTypeRepository:
    collection_name = "business_type_configs"

    async def get_all(self, only_active: bool = True) -> List[BusinessTypeConfig]:
        """Get all business type configurations."""
        db = get_database()
        query = {"isActive": True} if only_active else {}
        cursor = db[self.collection_name].find(query).sort("sortOrder", 1)
        configs = await cursor.to_list(length=None)
        return [BusinessTypeConfig(**self._convert_id(c)) for c in configs]

    async def get_by_id(self, config_id: str) -> Optional[BusinessTypeConfig]:
        """Get business type configuration by ID."""
        db = get_database()
        config = await db[self.collection_name].find_one({"_id": config_id})
        return BusinessTypeConfig(**self._convert_id(config)) if config else None

    async def get_by_key(self, key: str) -> Optional[BusinessTypeConfig]:
        """Get business type configuration by key."""
        db = get_database()
        config = await db[self.collection_name].find_one({"key": key})
        return BusinessTypeConfig(**self._convert_id(config)) if config else None

    async def get_modified_since(self, last_sync_at: datetime, only_active: bool = True) -> List[BusinessTypeConfig]:
        """Get business type configurations modified after a specific date."""
        db = get_database()
        query = {"updatedAt": {"$gt": last_sync_at}}
        if only_active:
            query["isActive"] = True
        cursor = db[self.collection_name].find(query).sort("sortOrder", 1)
        configs = await cursor.to_list(length=None)
        return [BusinessTypeConfig(**self._convert_id(c)) for c in configs]

    async def create(self, config_data: Dict[str, Any]) -> BusinessTypeConfig:
        """Create a new business type configuration."""
        db = get_database()
        now = datetime.utcnow()
        config_data["createdAt"] = now
        config_data["updatedAt"] = now
        
        # Generate ID from key
        config_data["_id"] = f"bt_{config_data['key'].lower()}"
        
        result = await db[self.collection_name].insert_one(config_data)
        return await self.get_by_id(config_data["_id"])

    async def update(self, config_id: str, update_data: Dict[str, Any]) -> Optional[BusinessTypeConfig]:
        """Update a business type configuration."""
        db = get_database()
        update_data["updatedAt"] = datetime.utcnow()
        
        await db[self.collection_name].update_one(
            {"_id": config_id},
            {"$set": update_data}
        )
        return await self.get_by_id(config_id)

    async def deactivate(self, config_id: str) -> Optional[BusinessTypeConfig]:
        """Soft delete a business type configuration."""
        return await self.update(config_id, {"isActive": False})

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string if needed."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc


# Singleton instance
business_type_repo = BusinessTypeRepository()
