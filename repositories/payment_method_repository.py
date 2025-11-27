"""Payment method repository for database operations."""
from typing import List, Optional, Dict, Any
from bson import ObjectId
from clients import get_database
from models import PaymentMethod


class PaymentMethodRepository:
    collection_name = "payment_methods"

    async def get_all(self) -> List[PaymentMethod]:
        db = get_database()
        cursor = db[self.collection_name].find()
        payment_methods = await cursor.to_list(length=None)
        return [PaymentMethod(**self._convert_id(pm)) for pm in payment_methods]

    async def get_by_id(self, payment_method_id: str) -> Optional[PaymentMethod]:
        db = get_database()
        # Convert string ID to ObjectId for MongoDB query
        try:
            object_id = ObjectId(payment_method_id)
        except:
            object_id = payment_method_id
        payment_method = await db[self.collection_name].find_one({"_id": object_id})
        return PaymentMethod(**self._convert_id(payment_method)) if payment_method else None

    async def get_by_ids(self, payment_method_ids: List[str]) -> List[PaymentMethod]:
        """Get multiple payment methods by their IDs."""
        db = get_database()
        # Convert string IDs to ObjectIds for MongoDB query
        object_ids = []
        for pm_id in payment_method_ids:
            try:
                object_ids.append(ObjectId(pm_id))
            except:
                object_ids.append(pm_id)

        cursor = db[self.collection_name].find({"_id": {"$in": object_ids}})
        payment_methods = await cursor.to_list(length=None)
        return [PaymentMethod(**self._convert_id(pm)) for pm in payment_methods]

    async def get_by_currency(self, currency: str) -> List[PaymentMethod]:
        """Get payment methods by currency (e.g., 'CUP', 'USD')."""
        db = get_database()
        cursor = db[self.collection_name].find({"currency": currency})
        payment_methods = await cursor.to_list(length=None)
        return [PaymentMethod(**self._convert_id(pm)) for pm in payment_methods]

    async def get_by_method(self, method: str) -> List[PaymentMethod]:
        """Get payment methods by method type (e.g., 'tarjeta', 'efectivo')."""
        db = get_database()
        cursor = db[self.collection_name].find({"method": method})
        payment_methods = await cursor.to_list(length=None)
        return [PaymentMethod(**self._convert_id(pm)) for pm in payment_methods]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
