"""Repository for TronDealer wallet records."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients import get_database
from domain.crypto_payments import TronDealerWallet, TronDealerWalletStatus


class TronDealerRepository:
    """CRUD and lookup operations for TronDealer assigned wallets."""

    @property
    def _col(self):
        return get_database()["trondealer_wallets"]

    async def create(self, wallet: TronDealerWallet) -> TronDealerWallet:
        doc = wallet.model_dump(by_alias=True)
        doc["_id"] = ObjectId()
        await self._col.insert_one(doc)
        return TronDealerWallet(**doc)

    async def get_by_id(self, wallet_id: str) -> Optional[TronDealerWallet]:
        doc = await self._col.find_one({"_id": ObjectId(wallet_id)})
        return TronDealerWallet(**doc) if doc else None

    async def get_by_order_id(self, order_id: str) -> Optional[TronDealerWallet]:
        doc = await self._col.find_one({"orderId": ObjectId(order_id)})
        return TronDealerWallet(**doc) if doc else None

    async def get_by_address(self, address: str) -> Optional[TronDealerWallet]:
        """Lookup by wallet address — used for webhook routing and idempotency."""
        doc = await self._col.find_one({"address": address})
        return TronDealerWallet(**doc) if doc else None

    async def mark_completed(
        self,
        address: str,
        received_amount: float,
        tx_hash: str,
        token: str,
        confirmations: int,
    ) -> Optional[TronDealerWallet]:
        """
        Mark wallet as completed idempotently.
        Returns None if wallet was already completed (duplicate webhook).
        """
        now = datetime.utcnow()
        result = await self._col.find_one_and_update(
            {
                "address": address,
                "status": TronDealerWalletStatus.PENDING,  # guard against duplicates
            },
            {
                "$set": {
                    "status": TronDealerWalletStatus.COMPLETED,
                    "receivedAmount": received_amount,
                    "txHash": tx_hash,
                    "token": token,
                    "confirmations": confirmations,
                    "completedAt": now,
                    "webhookReceivedAt": now,
                    "updatedAt": now,
                }
            },
            return_document=True,
        )
        return TronDealerWallet(**result) if result else None

    async def mark_expired(self, address: str) -> None:
        now = datetime.utcnow()
        await self._col.update_one(
            {"address": address},
            {"$set": {"status": TronDealerWalletStatus.EXPIRED, "updatedAt": now}},
        )

    async def get_pending(self, limit: int = 100) -> List[TronDealerWallet]:
        cursor = self._col.find(
            {"status": TronDealerWalletStatus.PENDING}
        ).sort("createdAt", 1).limit(limit)
        return [TronDealerWallet(**doc) async for doc in cursor]


trondealer_wallets_repo = TronDealerRepository()
