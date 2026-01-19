"""Wallet transaction repository for database operations."""
from typing import List, Optional
from clients import get_database
from models import WalletTransaction


class WalletTransactionRepository:
    collection_name = "wallet_transactions"

    async def create(self, transaction_data: dict) -> WalletTransaction:
        """Create a new wallet transaction."""
        db = get_database()
        await db[self.collection_name].insert_one(transaction_data)
        return WalletTransaction(**transaction_data)

    async def get_by_id(self, transaction_id: str) -> Optional[WalletTransaction]:
        """Get transaction by ID."""
        db = get_database()
        transaction = await db[self.collection_name].find_one({"_id": transaction_id})
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
                {"fromOwnerId": owner_id, "fromOwnerType": owner_type},
                {"toOwnerId": owner_id, "toOwnerType": owner_type}
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
