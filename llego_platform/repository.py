"""Platform repository for database operations."""
from typing import Optional
from datetime import datetime
from clients.mongodb_client import get_database
from .models import Platform, PlatformWallet


# Platform document ID (singleton)
PLATFORM_ID = "platform"


class PlatformRepository:
    """Repository for platform operations."""

    collection_name = "platform"

    def _get_collection(self):
        return get_database()[self.collection_name]

    async def get(self) -> Platform:
        """
        Get the platform document. Creates it if it doesn't exist.
        This is a singleton - there's only one platform document.
        """
        collection = self._get_collection()
        doc = await collection.find_one({"_id": PLATFORM_ID})

        if not doc:
            # Create the platform document if it doesn't exist
            platform = Platform()
            await collection.insert_one(platform.model_dump(by_alias=True))
            return platform

        return Platform(**doc)

    async def get_wallet_balance(self) -> PlatformWallet:
        """Get the platform wallet balance."""
        platform = await self.get()
        return platform.wallet

    async def add_commission(
        self,
        amount: float,
        currency: str,
    ) -> Platform:
        """
        Add commission to platform wallet.

        Args:
            amount: Commission amount
            currency: "local" or "usd"
        """
        collection = self._get_collection()

        # Ensure platform exists
        await self.get()

        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$inc": {
                    f"wallet.{currency}": amount,
                    "totalCommissionsCollected": amount if currency == "usd" else 0,
                },
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )

        return Platform(**result)

    async def increment_orders_processed(self) -> None:
        """Increment the total orders processed counter."""
        collection = self._get_collection()
        await collection.update_one(
            {"_id": PLATFORM_ID},
            {
                "$inc": {"totalOrdersProcessed": 1},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )

    async def withdraw_commission(
        self,
        amount: float,
        currency: str,
    ) -> Optional[Platform]:
        """
        Withdraw commission from platform wallet.

        Args:
            amount: Amount to withdraw
            currency: "local" or "usd"

        Returns:
            Updated platform or None if insufficient balance
        """
        collection = self._get_collection()

        result = await collection.find_one_and_update(
            {
                "_id": PLATFORM_ID,
                f"wallet.{currency}": {"$gte": amount},
            },
            {
                "$inc": {f"wallet.{currency}": -amount},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )

        return Platform(**result) if result else None
