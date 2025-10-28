"""Payment repository for database operations."""
from typing import List, Optional, Dict, Any
from clients import get_database
from models import SmsOcr
from datetime import datetime


class PaymentRepository:
    collection_name = "pagos"

    async def get_all(self) -> List[SmsOcr]:
        db = get_database()
        cursor = db[self.collection_name].find()
        payments = await cursor.to_list(length=None)
        return [SmsOcr(**self._convert_id(payment)) for payment in payments]

    async def get_by_id(self, payment_id: str) -> Optional[SmsOcr]:
        db = get_database()
        payment = await db[self.collection_name].find_one({"_id": payment_id})
        return SmsOcr(**self._convert_id(payment)) if payment else None

    async def create(self, payment_data: Dict[str, Any]) -> SmsOcr:
        """Crea un nuevo pago en la base de datos."""
        db = get_database()
        # Generar un ID único si no existe
        if "_id" not in payment_data:
            from bson import ObjectId
            payment_data["_id"] = str(ObjectId())

        # Asegurar que tiene fecha de creación
        if "createdAt" not in payment_data:
            payment_data["createdAt"] = datetime.utcnow()

        await db[self.collection_name].insert_one(payment_data)
        return SmsOcr(**self._convert_id(payment_data))

    async def get_by_banco(self, banco: str) -> List[SmsOcr]:
        """Obtiene pagos filtrados por banco."""
        db = get_database()
        cursor = db[self.collection_name].find({"banco": banco})
        payments = await cursor.to_list(length=None)
        return [SmsOcr(**self._convert_id(payment)) for payment in payments]

    async def get_by_numero_transferencia(self, numero: str) -> Optional[SmsOcr]:
        """Obtiene un pago por número de transferencia."""
        db = get_database()
        payment = await db[self.collection_name].find_one({"numero_transferencia": numero})
        return SmsOcr(**self._convert_id(payment)) if payment else None

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
