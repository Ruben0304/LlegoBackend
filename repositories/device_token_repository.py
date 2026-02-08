"""Device token repository for push notification management."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from clients import get_database
from domain.business_types import DeviceToken, DevicePlatform


class DeviceTokenRepository:
    collection_name = "device_tokens"

    async def get_all_active(self) -> List[DeviceToken]:
        """Get all active device tokens."""
        db = get_database()
        cursor = db[self.collection_name].find({"isActive": True})
        tokens = await cursor.to_list(length=None)
        return [DeviceToken(**self._convert_id(t)) for t in tokens]

    async def get_by_token(self, token: str) -> Optional[DeviceToken]:
        """Get device token by token string."""
        db = get_database()
        device = await db[self.collection_name].find_one({"token": token})
        return DeviceToken(**self._convert_id(device)) if device else None

    async def get_by_user_id(self, user_id: str) -> List[DeviceToken]:
        """Get all device tokens for a specific user."""
        db = get_database()
        cursor = db[self.collection_name].find({"userId": user_id, "isActive": True})
        tokens = await cursor.to_list(length=None)
        return [DeviceToken(**self._convert_id(t)) for t in tokens]

    async def create_or_update(self, token_data: Dict[str, Any]) -> DeviceToken:
        """Create or update a device token."""
        db = get_database()
        now = datetime.utcnow()
        
        # Check if token already exists
        existing = await self.get_by_token(token_data["token"])
        
        if existing:
            # Update existing token
            update_data = {
                "userId": token_data.get("userId"),
                "platform": token_data["platform"],
                "appVersion": token_data.get("appVersion"),
                "osVersion": token_data.get("osVersion"),
                "isActive": True,
                "updatedAt": now
            }
            await db[self.collection_name].update_one(
                {"token": token_data["token"]},
                {"$set": update_data}
            )
            return await self.get_by_token(token_data["token"])
        else:
            # Create new token
            token_data["_id"] = str(ObjectId())
            token_data["createdAt"] = now
            token_data["updatedAt"] = now
            token_data["isActive"] = True
            
            await db[self.collection_name].insert_one(token_data)
            return DeviceToken(**self._convert_id(token_data))

    async def deactivate(self, token: str) -> bool:
        """Deactivate a device token."""
        db = get_database()
        result = await db[self.collection_name].update_one(
            {"token": token},
            {"$set": {"isActive": False, "updatedAt": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def deactivate_user_tokens(self, user_id: str) -> int:
        """Deactivate all tokens for a user."""
        db = get_database()
        result = await db[self.collection_name].update_many(
            {"userId": user_id},
            {"$set": {"isActive": False, "updatedAt": datetime.utcnow()}}
        )
        return result.modified_count

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string if needed."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc


# Singleton instance
device_token_repo = DeviceTokenRepository()
