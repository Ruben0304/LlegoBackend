"""User repository for database operations."""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from bson import ObjectId

from clients import get_database
from domain.models import User


class UserRepository:
    collection_name = "users"

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

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

    async def username_exists(
        self, username: str, exclude_user_id: Optional[str] = None
    ) -> bool:
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

    async def search(self, query: str, limit: int = 50) -> List[User]:
        db = get_database()
        collection = db[self.collection_name]

        # Try text index search first (requires a text index on name+email).
        # Falls back to regex if the text index doesn't exist yet.
        try:
            cursor = (
                collection.find(
                    {"$text": {"$search": query}},
                    {"score": {"$meta": "textScore"}},
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
            users = await cursor.to_list(length=limit)
            if users:
                return [User(**self._convert_id(user)) for user in users]
        except Exception:
            pass

        # Fallback: anchored regex (prefix match) which can use a regular index
        import re

        escaped = re.escape(query)
        cursor = collection.find(
            {
                "$or": [
                    {"name": {"$regex": escaped, "$options": "i"}},
                    {"email": {"$regex": escaped, "$options": "i"}},
                ]
            }
        ).limit(limit)
        users = await cursor.to_list(length=limit)
        return [User(**self._convert_id(user)) for user in users]

    async def ensure_indexes(self):
        """Create text index on name and email for efficient search."""
        db = get_database()
        collection = db[self.collection_name]
        await collection.create_index(
            [("name", "text"), ("email", "text")],
            name="users_text_search",
            default_language="spanish",
        )

    async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update a user in MongoDB."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id}, {"$set": updates}, return_document=True
        )
        return User(**self._convert_id(result)) if result else None

    async def increment_delivered_orders_count(self, user_id: str) -> Optional[User]:
        """Atomically increment denormalized delivered orders counter."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$inc": {"deliveredOrdersCount": 1}},
            return_document=True,
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
            {"$addToSet": {"businessIds": self._to_object_id(business_id)}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_business_id(
        self, user_id: str, business_id: str
    ) -> Optional[User]:
        """Remove a business ID from the user's businessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"businessIds": self._to_object_id(business_id)}},
            return_document=True,
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
            {"$addToSet": {"branchIds": self._to_object_id(branch_id)}},
            return_document=True,
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
            {"$pull": {"branchIds": self._to_object_id(branch_id)}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def add_business_access_id(
        self, user_id: str, access_id: str
    ) -> Optional[User]:
        """Add a business access ID to the user's businessAccessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$addToSet": {"businessAccessIds": self._to_object_id(access_id)}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_business_access_id(
        self, user_id: str, access_id: str
    ) -> Optional[User]:
        """Remove a business access ID from the user's businessAccessIds list."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"businessAccessIds": self._to_object_id(access_id)}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def update_location(
        self, user_id: str, longitude: float, latitude: float
    ) -> Optional[User]:
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
                        "coordinates": [longitude, latitude],  # [lon, lat]
                    }
                }
            },
            return_document=True,
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

    # ------------------------------------------------------------------
    # Saved Addresses
    # ------------------------------------------------------------------

    async def add_saved_address(self, user_id: str, address: dict) -> Optional[User]:
        """Push a new saved address into the user's savedAddresses array."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$push": {"savedAddresses": address}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def remove_saved_address(
        self, user_id: str, address_id: str
    ) -> Optional[User]:
        """Pull a saved address by its id from the user's savedAddresses array."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$pull": {"savedAddresses": {"id": address_id}}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def update_saved_address(
        self, user_id: str, address_id: str, updated_address: dict
    ) -> Optional[User]:
        """Replace a saved address in-place using the positional $ operator."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "savedAddresses.id": address_id},
            {"$set": {"savedAddresses.$": updated_address}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def set_default_address(
        self, user_id: str, address_id: Optional[str]
    ) -> Optional[User]:
        """Set (or unset) the user's default delivery address."""
        db = get_database()
        try:
            object_id = ObjectId(user_id)
        except Exception:
            object_id = user_id

        result = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": {"defaultAddressId": address_id}},
            return_document=True,
        )
        return User(**self._convert_id(result)) if result else None

    async def get_wallet(self, user_id: str) -> Optional[Dict[str, float]]:
        """Get user wallet balance."""
        user = await self.get_by_id(user_id)
        return user.wallet if user else None

    async def update_wallet(
        self, user_id: str, currency: str, amount: float
    ) -> Optional[User]:
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

    async def increment_wallet(
        self, user_id: str, currency: str, amount: float
    ) -> Optional[User]:
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
            return_document=True,
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

    # ------------------------------------------------------------------
    # Admin metrics
    # ------------------------------------------------------------------

    async def get_metrics_sources(self, active_since: datetime) -> Dict[str, Any]:
        """Gather the raw sets/counts the user metrics are computed from.

        Segment membership is derived by joining other collections because
        `User.role` is always "customer" (see services/user_metrics for why).

        "Active" is the union of two things: the `lastSeenAt` we now record
        (schema/extensions.LastSeenExtension) and behavioural proxies that
        already existed — orders placed, searches run, and courier records
        touched by location/online updates. The union is what makes this metric
        meaningful before `lastSeenAt` has had time to accumulate.
        """
        db = get_database()

        (
            total_users,
            new_users,
            last_seen_ids,
            courier_ids,
            active_courier_ids,
            owner_ids,
            manager_id_lists,
            access_user_ids,
            ordering_ids,
            searching_ids,
        ) = await asyncio.gather(
            db[self.collection_name].count_documents({}),
            db[self.collection_name].count_documents(
                {"createdAt": {"$gte": active_since}}
            ),
            db[self.collection_name].distinct(
                "_id", {"lastSeenAt": {"$gte": active_since}}
            ),
            db["delivery_persons"].distinct("userId"),
            db["delivery_persons"].distinct(
                "userId", {"updatedAt": {"$gte": active_since}}
            ),
            # Intentional misspelling of the businesses collection — see CLAUDE.md.
            db["bussisnes"].distinct("ownerId"),
            db["branches"].distinct("managerIds"),
            db["business_access"].distinct("userId", {"isActive": True}),
            db["orders"].distinct("customerId", {"createdAt": {"$gte": active_since}}),
            db["searches"].distinct("userId", {"createdAt": {"$gte": active_since}}),
        )

        def as_str_set(*id_lists) -> Set[str]:
            out: Set[str] = set()
            for ids in id_lists:
                for value in ids or []:
                    if value is not None:
                        out.add(str(value))
            return out

        return {
            "total_users": total_users,
            "new_users": new_users,
            "courier_ids": as_str_set(courier_ids),
            "business_ids": as_str_set(owner_ids, manager_id_lists, access_user_ids),
            "active_ids": as_str_set(
                last_seen_ids, active_courier_ids, ordering_ids, searching_ids
            ),
        }

    async def list_segment(
        self,
        *,
        spec: Dict[str, Any],
        since: datetime,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple:
        """Page through the users of one segment, newest signups first.

        `spec` comes from services.user_metrics.build_segment_spec, so the list
        behind a metrics card is always the same set the card counted.
        """
        db = get_database()
        query: Dict[str, Any] = {}

        include_ids = spec.get("include_ids")
        if include_ids is not None:
            # An empty segment must return nothing, not everything.
            query["_id"] = {"$in": [self._to_object_id(i) for i in include_ids]}

        exclude_ids = spec.get("exclude_ids")
        if exclude_ids:
            query.setdefault("_id", {})["$nin"] = [
                self._to_object_id(i) for i in exclude_ids
            ]

        if spec.get("only_new"):
            query["createdAt"] = {"$gte": since}

        if search:
            escaped = re.escape(search.strip())
            if escaped:
                query["$or"] = [
                    {"name": {"$regex": escaped, "$options": "i"}},
                    {"email": {"$regex": escaped, "$options": "i"}},
                    {"phone": {"$regex": escaped, "$options": "i"}},
                ]

        collection = db[self.collection_name]
        total = await collection.count_documents(query)
        cursor = (
            collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [User(**self._convert_id(d)) for d in docs], total

    async def get_signups_by_day(self, since: datetime) -> List[Dict[str, Any]]:
        """Registrations per day, oldest first.

        First time-series aggregation in the backend — everything else that
        needed one (e.g. the Panel Admin orders chart) resorted to N queries,
        one per day.
        """
        db = get_database()
        pipeline = [
            {"$match": {"createdAt": {"$gte": since}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        rows = await db[self.collection_name].aggregate(pipeline).to_list(None)
        return [{"day": r["_id"], "count": r["count"]} for r in rows]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
