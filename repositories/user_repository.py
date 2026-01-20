"""User repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import User


class UserRepository:
    collection_name = "users"

    async def get_all(self) -> List[User]:
        db = get_database()
        cursor = db[self.collection_name].find()
        users = await cursor.to_list(length=None)
        return [User(**self._convert_id(user)) for user in users]

    async def get_by_id(self, user_id: str) -> Optional[User]:
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id
        user = await db[self.collection_name].find_one({"_id": object_id})
        return User(**self._convert_id(user)) if user else None

    async def get_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        db = get_database()
        user = await db[self.collection_name].find_one({"username": username})
        return User(**self._convert_id(user)) if user else None

    async def username_exists(self, username: str, exclude_user_id: Optional[str] = None) -> bool:
        """Check if username already exists (excluding a specific user ID)."""
        db = get_database()
        query = {"username": username}
        if exclude_user_id:
            try:
                object_id = ObjectId(exclude_user_id)
            except Exception:
                object_id = exclude_user_id
            query["_id"] = {"$ne": object_id}
        
        user = await db[self.collection_name].find_one(query)
        return user is not None

    async def search(self, query: str) -> List[User]:
        db = get_database()
        cursor = db[self.collection_name].find({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}}
            ]
        })
        users = await cursor.to_list(length=None)
        return [User(**self._convert_id(user)) for user in users]

    async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update a user in MongoDB."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": updates},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def add_business_id(self, user_id: str, business_id: str) -> Optional[User]:
        """Add a business ID to the user's businessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$addToSet": {"businessIds": business_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_business_id(self, user_id: str, business_id: str) -> Optional[User]:
        """Remove a business ID from the user's businessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"businessIds": business_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def add_branch_id(self, user_id: str, branch_id: str) -> Optional[User]:
        """Add a branch ID to the user's branchIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$addToSet": {"branchIds": branch_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_branch_id(self, user_id: str, branch_id: str) -> Optional[User]:
        """Remove a branch ID from the user's branchIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"branchIds": branch_id}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def update_location(self, user_id: str, longitude: float, latitude: float) -> Optional[User]:
        """
        Update user location.
        
        Args:
            user_id: The user ID
            longitude: Longitude coordinate (X)
            latitude: Latitude coordinate (Y)
            
        Returns:
            Updated user or None
        """
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "location": {
                        "type": "Point",
                        "coordinates": [longitude, latitude]  # [lon, lat]
                    }
                }
            },
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def get_location(self, user_id: str) -> Optional[tuple]:
        """
        Get user coordinates as (longitude, latitude) tuple.
        
        Returns:
            Tuple of (longitude, latitude) or None if not found
        """
        user = await self.get_by_id(user_id)
        if user and user.location:
            coords = user.location.get("coordinates", [])
            if len(coords) == 2:
                return (coords[0], coords[1])  # (lon, lat)
        return None

    async def delete(self, user_id: str) -> bool:
        """Delete a user from MongoDB."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def get_wallet(self, user_id: str) -> Optional[Dict[str, float]]:
        """Get user wallet balance."""
        user = await self.get_by_id(user_id)
        return user.wallet if user else None

    async def update_wallet(self, user_id: str, currency: str, amount: float) -> Optional[User]:
        """
        Update user wallet balance for a specific currency.

        Args:
            user_id: The user ID
            currency: Currency type ('local' or 'usd')
            amount: New amount to set

        Returns:
            Updated user or None
        """
        return await self.update(user_id, {f"wallet.{currency}": amount})

    async def increment_wallet(self, user_id: str, currency: str, amount: float) -> Optional[User]:
        """
        Increment user wallet balance for a specific currency.

        Args:
            user_id: The user ID
            currency: Currency type ('local' or 'usd')
            amount: Amount to increment (can be negative for decrement)

        Returns:
            Updated user or None
        """
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$inc": {f"wallet.{currency}": amount}},
            return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def update_wallet_status(self, user_id: str, status: str) -> Optional[User]:
        """
        Update user wallet status.

        Args:
            user_id: The user ID
            status: New wallet status ('active', 'frozen', 'closed')

        Returns:
            Updated user or None
        """
        return await self.update(user_id, {"walletStatus": status})

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
