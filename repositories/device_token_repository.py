"""Device token repository for push notification management."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from clients import get_database
from domain.business_types import DeviceToken, DevicePlatform

# Apps que registran tokens. Un token sin bundleId es de la app de clientes
# (LlegoiOS / LlegoApk registran sin bundleId).
AUDIENCE_CUSTOMER = "customer"
AUDIENCE_BUSINESS = "business"
BUSINESS_BUNDLE_PREFIX = "com.llego.business"
BUSINESS_IOS_BUNDLE_ID = "com.llego.business.LlegoBusiness"


def token_audience(token: DeviceToken) -> str:
    bundle_id = token.bundleId or ""
    if bundle_id.startswith(BUSINESS_BUNDLE_PREFIX):
        return AUDIENCE_BUSINESS
    return AUDIENCE_CUSTOMER


def _filter_audience(tokens: List[DeviceToken], audience: Optional[str]) -> List[DeviceToken]:
    if audience is None:
        return tokens
    return [t for t in tokens if token_audience(t) == audience]


class DeviceTokenRepository:
    collection_name = "device_tokens"

    @staticmethod
    def _to_object_id(value: Optional[str]):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def get_all_active(self, audience: Optional[str] = None) -> List[DeviceToken]:
        """Get all active device tokens, optionally only those of one app (audience)."""
        db = get_database()
        cursor = db[self.collection_name].find({"isActive": True})
        tokens = await cursor.to_list(length=None)
        return _filter_audience([DeviceToken(**self._convert_id(t)) for t in tokens], audience)

    async def get_by_token(self, token: str) -> Optional[DeviceToken]:
        """Get device token by token string."""
        db = get_database()
        device = await db[self.collection_name].find_one({"token": token})
        return DeviceToken(**self._convert_id(device)) if device else None

    async def get_by_user_id(
        self, user_id: str, audience: Optional[str] = None
    ) -> List[DeviceToken]:
        """Get active device tokens for a user, optionally only those of one app (audience)."""
        db = get_database()
        cursor = db[self.collection_name].find(
            {"userId": self._to_object_id(user_id), "isActive": True}
        )
        tokens = await cursor.to_list(length=None)
        return _filter_audience([DeviceToken(**self._convert_id(t)) for t in tokens], audience)

    async def get_by_user_ids(
        self, user_ids: List[str], audience: Optional[str] = None
    ) -> List[DeviceToken]:
        """Get active device tokens for several users, optionally filtered by audience."""
        if not user_ids:
            return []
        db = get_database()
        cursor = db[self.collection_name].find(
            {
                "userId": {"$in": [self._to_object_id(uid) for uid in user_ids]},
                "isActive": True,
            }
        )
        tokens = await cursor.to_list(length=None)
        return _filter_audience([DeviceToken(**self._convert_id(t)) for t in tokens], audience)

    async def create_or_update(self, token_data: Dict[str, Any]) -> DeviceToken:
        """Create or update a device token."""
        db = get_database()
        now = datetime.utcnow()
        
        # Check if token already exists
        existing = await self.get_by_token(token_data["token"])
        
        if existing:
            # Update existing token
            update_data = {
                "userId": self._to_object_id(token_data.get("userId")),
                "platform": token_data["platform"],
                "appVersion": token_data.get("appVersion"),
                "osVersion": token_data.get("osVersion"),
                "isActive": True,
                "updatedAt": now
            }
            # Solo sobrescribir bundleId si el cliente lo envía (clientes viejos no lo mandan)
            if token_data.get("bundleId"):
                update_data["bundleId"] = token_data["bundleId"]
            await db[self.collection_name].update_one(
                {"token": token_data["token"]},
                {"$set": update_data}
            )
            return await self.get_by_token(token_data["token"])
        else:
            # Create new token
            token_data["_id"] = ObjectId()
            token_data["userId"] = self._to_object_id(token_data.get("userId"))
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
            {"userId": self._to_object_id(user_id)},
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
