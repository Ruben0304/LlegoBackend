"""Payment repository for database operations."""
from typing import List, Optional, Dict, Any, Tuple
from bson import ObjectId
from clients import get_database
from domain.models import SmsOcr
from datetime import datetime


class PaymentRepository:
    collection_name = "pagos"

    @staticmethod
    def _to_object_id(value: str):
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def get_all(self) -> List[SmsOcr]:
        db = get_database()
        cursor = db[self.collection_name].find()
        payments = await cursor.to_list(length=None)
        return [SmsOcr(**self._convert_id(payment)) for payment in payments]

    async def get_by_id(self, payment_id: str) -> Optional[SmsOcr]:
        db = get_database()
        payment = await db[self.collection_name].find_one(
            {"_id": self._to_object_id(payment_id)}
        )
        return SmsOcr(**self._convert_id(payment)) if payment else None

    async def create(self, payment_data: Dict[str, Any]) -> SmsOcr:
        """Crea un nuevo pago en la base de datos."""
        db = get_database()
        payment_doc = dict(payment_data)
        # Generar un ID único si no existe
        if "_id" not in payment_doc:
            payment_doc["_id"] = ObjectId()
        else:
            payment_doc["_id"] = self._to_object_id(payment_doc["_id"])

        # Asegurar que tiene fecha de creación
        if "createdAt" not in payment_doc:
            payment_doc["createdAt"] = datetime.utcnow()

        await db[self.collection_name].insert_one(payment_doc)
        return SmsOcr(**self._convert_id(payment_doc))

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

    async def list_filtered(
        self,
        *,
        banco: Optional[str] = None,
        numero_transferencia: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[SmsOcr], int]:
        """Lista pagos OCR (colección `pagos`) con filtros y paginación."""
        db = get_database()
        query: Dict[str, Any] = {}

        if banco:
            query["banco"] = banco
        if numero_transferencia:
            query["numero_transferencia"] = numero_transferencia

        if from_date or to_date:
            # Preferimos filtrar por `createdAt` que siempre se setea en create()
            query.setdefault("createdAt", {})
            if from_date:
                query["createdAt"]["$gte"] = from_date
            if to_date:
                query["createdAt"]["$lte"] = to_date

        total = await db[self.collection_name].count_documents(query)
        cursor = (
            db[self.collection_name]
            .find(query)
            .sort("createdAt", -1)
            .skip(offset)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [SmsOcr(**self._convert_id(d)) for d in docs], total

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
