"""Wallet transaction repository for database operations."""
from typing import List, Optional
from datetime import datetime
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


class WalletRepository:
    """Repository for wallet balance operations."""
    
    async def add_balance(
        self,
        user_id: str,
        amount: float,
        transaction_type: str = "stripe_recharge",
        reference_id: str = None
    ) -> bool:
        """
        Add balance to user wallet.
        
        Args:
            user_id: User ID
            amount: Amount to add (in dollars)
            transaction_type: Type of transaction (e.g., 'stripe_recharge')
            reference_id: External reference (e.g., Stripe payment intent ID)
        
        Returns:
            True if successful
        """
        db = get_database()
        
        # Update user wallet balance
        result = await db["users"].update_one(
            {"_id": user_id},
            {
                "$inc": {"wallet.balance": amount},
                "$set": {"wallet.updatedAt": datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            return False
        
        # Create transaction record
        transaction_data = {
            "_id": reference_id or f"stripe_{user_id}_{datetime.utcnow().timestamp()}",
            "fromOwnerId": "system",
            "fromOwnerType": "system",
            "toOwnerId": user_id,
            "toOwnerType": "user",
            "amount": amount,
            "currency": "usd",
            "type": transaction_type,
            "status": "completed",
            "description": f"Stripe recharge: ${amount}",
            "metadata": {
                "payment_intent_id": reference_id,
                "source": "stripe"
            },
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        await db["wallet_transactions"].insert_one(transaction_data)
        
        return True
