"""Wallet service for managing wallet operations."""
from decimal import Decimal
from datetime import datetime
from typing import Optional, Literal, Dict
from uuid import uuid4
from fastapi import HTTPException

from clients.mongodb_client import get_database


class WalletService:
    """Service for wallet operations."""

    def __init__(self):
        self.db = get_database()

    async def get_balance(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"]
    ) -> Dict[str, float]:
        """Get wallet balance for a user or branch."""
        collection = self.db.users if owner_type == "user" else self.db.branches
        
        owner = await collection.find_one({"_id": owner_id})
        if not owner:
            raise HTTPException(status_code=404, detail=f"{owner_type.capitalize()} not found")
        
        # Get wallet or return default values
        wallet = owner.get("wallet", {"local": 0.00, "usd": 0.00})
        
        # If wallet doesn't exist in DB, create it
        if "wallet" not in owner:
            await collection.update_one(
                {"_id": owner_id},
                {"$set": {
                    "wallet": {"local": 0.00, "usd": 0.00},
                    "walletStatus": "active"
                }}
            )
        
        return wallet

    async def transfer(
        self,
        from_owner_id: str,
        from_owner_type: Literal["user", "branch"],
        to_owner_id: str,
        to_owner_type: Literal["user", "branch"],
        amount: Decimal,
        currency: Literal["local", "usd"],
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Transfer money between wallets.
        Uses MongoDB transaction for atomicity.
        """
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")

        # Get collections
        from_collection = self.db.users if from_owner_type == "user" else self.db.branches
        to_collection = self.db.users if to_owner_type == "user" else self.db.branches

        # Start MongoDB transaction
        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                # 1. Validate and deduct from sender
                from_owner = await from_collection.find_one({"_id": from_owner_id}, session=session)
                if not from_owner:
                    raise HTTPException(status_code=404, detail=f"Sender {from_owner_type} not found")
                
                if from_owner.get("walletStatus") != "active":
                    raise HTTPException(status_code=403, detail="Sender wallet is not active")

                from_balance = Decimal(str(from_owner.get("wallet", {}).get(currency, 0)))
                if from_balance < amount:
                    raise HTTPException(status_code=400, detail="Insufficient balance")

                # Deduct from sender using atomic operation
                result = await from_collection.update_one(
                    {
                        "_id": from_owner_id,
                        f"wallet.{currency}": {"$gte": float(amount)}
                    },
                    {"$inc": {f"wallet.{currency}": -float(amount)}},
                    session=session
                )
                
                if result.modified_count == 0:
                    raise HTTPException(status_code=400, detail="Insufficient balance or concurrent modification")

                # 2. Validate and add to receiver
                to_owner = await to_collection.find_one({"_id": to_owner_id}, session=session)
                if not to_owner:
                    raise HTTPException(status_code=404, detail=f"Receiver {to_owner_type} not found")
                
                if to_owner.get("walletStatus") != "active":
                    raise HTTPException(status_code=403, detail="Receiver wallet is not active")

                # Add to receiver
                await to_collection.update_one(
                    {"_id": to_owner_id},
                    {"$inc": {f"wallet.{currency}": float(amount)}},
                    session=session
                )

                # 3. Create transaction record
                transaction_id = str(uuid4())
                transaction = {
                    "_id": transaction_id,
                    "fromOwnerId": from_owner_id,
                    "fromOwnerType": from_owner_type,
                    "toOwnerId": to_owner_id,
                    "toOwnerType": to_owner_type,
                    "amount": float(amount),
                    "currency": currency,
                    "type": "transfer",
                    "status": "completed",
                    "description": description,
                    "metadata": metadata,
                    "createdAt": datetime.utcnow(),
                    "completedAt": datetime.utcnow()
                }
                
                await self.db.wallet_transactions.insert_one(transaction, session=session)

                return {
                    "transaction_id": transaction_id,
                    "status": "completed",
                    "from_owner_id": from_owner_id,
                    "to_owner_id": to_owner_id,
                    "amount": float(amount),
                    "currency": currency
                }

    async def deposit(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"],
        amount: Decimal,
        currency: Literal["local", "usd"],
        source: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Deposit money into a wallet from external source.
        For MVP: marks as completed immediately.
        In production: should be 'pending' until payment gateway confirms.
        """
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")

        collection = self.db.users if owner_type == "user" else self.db.branches

        # Validate owner exists and wallet is active
        owner = await collection.find_one({"_id": owner_id})
        if not owner:
            raise HTTPException(status_code=404, detail=f"{owner_type.capitalize()} not found")
        
        if owner.get("walletStatus") != "active":
            raise HTTPException(status_code=403, detail="Wallet is not active")

        # Start transaction
        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                # Add to wallet
                await collection.update_one(
                    {"_id": owner_id},
                    {"$inc": {f"wallet.{currency}": float(amount)}},
                    session=session
                )

                # Create transaction record
                transaction_id = str(uuid4())
                transaction = {
                    "_id": transaction_id,
                    "fromOwnerId": None,
                    "fromOwnerType": None,
                    "toOwnerId": owner_id,
                    "toOwnerType": owner_type,
                    "amount": float(amount),
                    "currency": currency,
                    "type": "deposit",
                    "status": "completed",  # For MVP, mark as completed immediately
                    "description": description or f"Deposit from {source}",
                    "metadata": {**(metadata or {}), "source": source},
                    "createdAt": datetime.utcnow(),
                    "completedAt": datetime.utcnow()
                }
                
                await self.db.wallet_transactions.insert_one(transaction, session=session)

                return {
                    "transaction_id": transaction_id,
                    "status": "completed",
                    "owner_id": owner_id,
                    "amount": float(amount),
                    "currency": currency
                }

    async def withdraw(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"],
        amount: Decimal,
        currency: Literal["local", "usd"],
        destination: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Withdraw money from wallet to external destination.
        For MVP: marks as pending until manual approval.
        """
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")

        collection = self.db.users if owner_type == "user" else self.db.branches

        # Start transaction
        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                # Validate and deduct from wallet
                owner = await collection.find_one({"_id": owner_id}, session=session)
                if not owner:
                    raise HTTPException(status_code=404, detail=f"{owner_type.capitalize()} not found")
                
                if owner.get("walletStatus") != "active":
                    raise HTTPException(status_code=403, detail="Wallet is not active")

                balance = Decimal(str(owner.get("wallet", {}).get(currency, 0)))
                if balance < amount:
                    raise HTTPException(status_code=400, detail="Insufficient balance")

                # Deduct from wallet
                result = await collection.update_one(
                    {
                        "_id": owner_id,
                        f"wallet.{currency}": {"$gte": float(amount)}
                    },
                    {"$inc": {f"wallet.{currency}": -float(amount)}},
                    session=session
                )
                
                if result.modified_count == 0:
                    raise HTTPException(status_code=400, detail="Insufficient balance or concurrent modification")

                # Create transaction record
                transaction_id = str(uuid4())
                transaction = {
                    "_id": transaction_id,
                    "fromOwnerId": owner_id,
                    "fromOwnerType": owner_type,
                    "toOwnerId": None,
                    "toOwnerType": None,
                    "amount": float(amount),
                    "currency": currency,
                    "type": "withdrawal",
                    "status": "pending",  # Pending until manual approval
                    "description": description or f"Withdrawal to {destination}",
                    "metadata": {**(metadata or {}), "destination": destination},
                    "createdAt": datetime.utcnow(),
                    "completedAt": None
                }
                
                await self.db.wallet_transactions.insert_one(transaction, session=session)

                return {
                    "transaction_id": transaction_id,
                    "status": "pending",
                    "owner_id": owner_id,
                    "amount": float(amount),
                    "currency": currency,
                    "message": "Withdrawal request submitted. Pending approval."
                }

    async def get_transaction_history(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"],
        limit: int = 50,
        skip: int = 0,
        currency: Optional[Literal["local", "usd"]] = None
    ) -> list:
        """Get transaction history for a wallet."""
        query = {
            "$or": [
                {"fromOwnerId": owner_id, "fromOwnerType": owner_type},
                {"toOwnerId": owner_id, "toOwnerType": owner_type}
            ]
        }
        
        if currency:
            query["currency"] = currency

        transactions = await self.db.wallet_transactions.find(query)\
            .sort("createdAt", -1)\
            .skip(skip)\
            .limit(limit)\
            .to_list(length=limit)

        return transactions

    async def freeze_wallet(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"]
    ) -> dict:
        """Freeze a wallet (admin operation)."""
        collection = self.db.users if owner_type == "user" else self.db.branches
        
        result = await collection.update_one(
            {"_id": owner_id},
            {"$set": {"walletStatus": "frozen"}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail=f"{owner_type.capitalize()} not found")
        
        return {"status": "frozen", "owner_id": owner_id}

    async def unfreeze_wallet(
        self,
        owner_id: str,
        owner_type: Literal["user", "branch"]
    ) -> dict:
        """Unfreeze a wallet (admin operation)."""
        collection = self.db.users if owner_type == "user" else self.db.branches
        
        result = await collection.update_one(
            {"_id": owner_id},
            {"$set": {"walletStatus": "active"}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail=f"{owner_type.capitalize()} not found")
        
        return {"status": "active", "owner_id": owner_id}


# Singleton instance
wallet_service = WalletService()
