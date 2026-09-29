"""Historial de notificaciones push enviadas desde el Panel Admin."""
from typing import Any, Dict, List, Tuple

from bson import ObjectId

from clients import get_database
from domain.admin_push import AdminPushNotification


class AdminPushRepository:
    collection_name = "admin_push_notifications"

    async def create(self, data: Dict[str, Any]) -> AdminPushNotification:
        db = get_database()
        doc = {**data, "_id": ObjectId(data["_id"]) if "_id" in data else ObjectId()}
        await db[self.collection_name].insert_one(doc)
        return AdminPushNotification(**{**doc, "_id": str(doc["_id"])})

    async def list_recent(
        self, skip: int = 0, limit: int = 20
    ) -> Tuple[List[AdminPushNotification], int]:
        db = get_database()
        collection = db[self.collection_name]
        total = await collection.count_documents({})
        cursor = collection.find().sort("createdAt", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [
            AdminPushNotification(**{**d, "_id": str(d["_id"])}) for d in docs
        ], total


admin_push_repo = AdminPushRepository()
