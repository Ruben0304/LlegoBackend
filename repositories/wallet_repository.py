"""Wallet transaction repository for database operations."""
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from clients import get_database
from domain.models import WalletTransaction


class WalletTransactionRepository:
    collection_name = "wallet_transactions"

    @staticmethod
    def _to_object_id(value: Optional[str]):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def create(self, transaction_data: dict) -> WalletTransaction:
        """Create a new wallet transaction."""
        db = get_database()
        await db[self.collection_name].insert_one(transaction_data)
        return WalletTransaction(**transaction_data)

    async def get_by_id(self, transaction_id: str) -> Optional[WalletTransaction]:
        """Get transaction by ID."""
        db = get_database()
        transaction = await db[self.collection_name].find_one(
            {"_id": self._to_object_id(transaction_id)}
        )
        return WalletTransaction(**transaction) if transaction else None

    async def get_by_owner(
        self,
        owner_id: str,
        owner_type: str,
        limit: int = 50,
        skip: int = 0,
        currency: Optional[str] = None
    ) -> List[WalletTransaction]:
        """Get transaction history for an owner."""
        db = get_database()
        query = {
            "$or": [
                {"fromOwnerId": self._to_object_id(owner_id), "fromOwnerType": owner_type},
                {"toOwnerId": self._to_object_id(owner_id), "toOwnerType": owner_type}
            ]
        }
        
        if currency:
            query["currency"] = currency

        cursor = db[self.collection_name].find(query)\
            .sort("createdAt", -1)\
            .skip(skip)\
            .limit(limit)
        
        transactions = await cursor.to_list(length=limit)
        return [WalletTransaction(**tx) for tx in transactions]


class WalletRepository:
    """Saldo de la billetera de usuario acreditado desde cobros externos (Stripe)."""

    async def add_balance(
        self,
        user_id: str,
        amount: float,
        transaction_type: str = "stripe_recharge",
        reference_id: str = None,
        currency: str = "usd",
    ) -> bool:
        """
        Acredita `amount` en users.wallet.<currency>, el mismo campo que leen WalletService
        y las apps (antes sumaba en un wallet.balance que nadie lee y además fallaba siempre).

        Stripe reintenta los webhooks: con `reference_id` el cobro se acredita una sola vez
        (índice único sobre externalReference). Devuelve False si no acreditó nada.
        """
        if amount is None or amount <= 0 or currency not in ("usd", "local"):
            return False

        db = get_database()
        user_oid = WalletTransactionRepository._to_object_id(user_id)
        if not await db["users"].find_one({"_id": user_oid}, {"_id": 1}):
            return False

        now = datetime.utcnow()
        transaction_data = {
            "fromOwnerId": None,
            "fromOwnerType": None,
            "toOwnerId": user_oid,
            "toOwnerType": "user",
            "amount": float(amount),
            "currency": currency,
            "type": "deposit",
            "status": "completed",
            "description": f"Recarga con Stripe: ${float(amount):.2f}",
            "metadata": {"source": "stripe", "kind": transaction_type, "payment_intent_id": reference_id},
            "createdAt": now,
            "completedAt": now,
        }

        if reference_id:
            # Primero el apunte (upsert por referencia) y solo si es nuevo se suma el saldo
            result = await db["wallet_transactions"].update_one(
                {"externalReference": reference_id},
                {"$setOnInsert": {**transaction_data, "externalReference": reference_id}},
                upsert=True,
            )
            if result.upserted_id is None:
                return False
        else:
            await db["wallet_transactions"].insert_one(transaction_data)

        await db["users"].update_one(
            {"_id": user_oid},
            {"$inc": {f"wallet.{currency}": float(amount)}},
        )
        return True
