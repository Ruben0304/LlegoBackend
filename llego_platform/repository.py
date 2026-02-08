"""Platform repository for database operations."""

from datetime import datetime
from typing import Dict, List, Optional

from clients.mongodb_client import get_database

from .models import Platform, PlatformWallet, QrPayment, TransferAccount, TransferPhone

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

    # =========================================================================
    # Transfer Accounts (CUP card accounts)
    # =========================================================================

    async def get_transfer_info(self) -> Dict:
        """Get all transfer payment info (accounts, qrPayments, phones)."""
        platform = await self.get()
        return {
            "accounts": platform.accounts,
            "qrPayments": platform.qrPayments,
            "phones": platform.phones,
        }

    async def add_account(self, account: TransferAccount) -> Platform:
        """Add a transfer account to the platform."""
        collection = self._get_collection()
        await self.get()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$push": {"accounts": account.model_dump()},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    async def update_account(
        self, card_number: str, updates: Dict
    ) -> Optional[Platform]:
        """Update a transfer account by card number."""
        collection = self._get_collection()
        set_fields = {f"accounts.$.{k}": v for k, v in updates.items()}
        set_fields["updatedAt"] = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID, "accounts.cardNumber": card_number},
            {"$set": set_fields},
            return_document=True,
        )
        return Platform(**result) if result else None

    async def remove_account(self, card_number: str) -> Platform:
        """Remove a transfer account by card number."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$pull": {"accounts": {"cardNumber": card_number}},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    # =========================================================================
    # QR Payments
    # =========================================================================

    async def add_qr_payment(self, qr: QrPayment) -> Platform:
        """Add a QR payment to the platform."""
        collection = self._get_collection()
        await self.get()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$push": {"qrPayments": qr.model_dump()},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    async def update_qr_payment(self, value: str, updates: Dict) -> Optional[Platform]:
        """Update a QR payment by its value."""
        collection = self._get_collection()
        set_fields = {f"qrPayments.$.{k}": v for k, v in updates.items()}
        set_fields["updatedAt"] = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID, "qrPayments.value": value},
            {"$set": set_fields},
            return_document=True,
        )
        return Platform(**result) if result else None

    async def remove_qr_payment(self, value: str) -> Platform:
        """Remove a QR payment by its value."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$pull": {"qrPayments": {"value": value}},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    # =========================================================================
    # Transfer Phones
    # =========================================================================

    async def add_phone(self, phone: TransferPhone) -> Platform:
        """Add a transfer phone to the platform."""
        collection = self._get_collection()
        await self.get()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$push": {"phones": phone.model_dump()},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    async def update_phone(self, phone: str, updates: Dict) -> Optional[Platform]:
        """Update a transfer phone by its number."""
        collection = self._get_collection()
        set_fields = {f"phones.$.{k}": v for k, v in updates.items()}
        set_fields["updatedAt"] = datetime.utcnow()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID, "phones.phone": phone},
            {"$set": set_fields},
            return_document=True,
        )
        return Platform(**result) if result else None

    async def remove_phone(self, phone: str) -> Platform:
        """Remove a transfer phone by its number."""
        collection = self._get_collection()
        result = await collection.find_one_and_update(
            {"_id": PLATFORM_ID},
            {
                "$pull": {"phones": {"phone": phone}},
                "$set": {"updatedAt": datetime.utcnow()},
            },
            return_document=True,
        )
        return Platform(**result)

    # =========================================================================
    # Withdrawals
    # =========================================================================

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
