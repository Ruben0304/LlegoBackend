"""
Migration script to update payment_methods collection with new fields
and create initial payment methods if they don't exist.

Run with: python scripts/migrate_payment_methods.py
"""
import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# MongoDB connection
MONGODB_URL = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627"
DATABASE_NAME = "llego"


# Initial payment methods
INITIAL_PAYMENT_METHODS = [
    {
        "_id": ObjectId(),
        "name": "Wallet USD",
        "code": "wallet_usd",
        "currency": "USD",
        "method": "wallet",
        "commissionPercent": 0.0,  # No commission for wallet
        "deliveryFeePercent": 0.0,
        "isRefundable": True,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": None,
        "isActive": True,
        "displayOrder": 1,
        "iconUrl": None,
        "instructions": None,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": ObjectId(),
        "name": "Wallet CUP",
        "code": "wallet_cup",
        "currency": "CUP",
        "method": "wallet",
        "commissionPercent": 0.0,
        "deliveryFeePercent": 0.0,
        "isRefundable": True,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": None,
        "isActive": True,
        "displayOrder": 2,
        "iconUrl": None,
        "instructions": None,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": ObjectId(),
        "name": "Stripe (Tarjeta)",
        "code": "stripe",
        "currency": "USD",
        "method": "stripe",
        "commissionPercent": 3.5,  # 3.5% commission
        "deliveryFeePercent": 0.0,
        "isRefundable": True,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": 30,  # 30 min to complete payment
        "isActive": True,
        "displayOrder": 3,
        "iconUrl": None,
        "instructions": None,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": ObjectId(),
        "name": "Transfermóvil",
        "code": "transfermovil",
        "currency": "CUP",
        "method": "transfer",
        "commissionPercent": 2.0,  # 2% commission
        "deliveryFeePercent": 0.0,
        "isRefundable": False,  # Manual transfers not refundable automatically
        "requiresProof": True,
        "requiresBusinessConfirmation": True,
        "expirationMinutes": 2880,  # 48 hours
        "isActive": True,
        "displayOrder": 4,
        "iconUrl": None,
        "instructions": "Realiza la transferencia al número de la tienda y sube el comprobante.",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": ObjectId(),
        "name": "Efectivo",
        "code": "cash",
        "currency": "CUP",
        "method": "cash",
        "commissionPercent": 0.0,
        "deliveryFeePercent": 5.0,  # 5% extra on delivery fee for cash
        "isRefundable": False,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": None,  # No expiration, waits for delivery
        "isActive": True,
        "displayOrder": 5,
        "iconUrl": None,
        "instructions": "Paga en efectivo al momento de la entrega.",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": ObjectId(),
        "name": "Efectivo USD",
        "code": "cash_usd",
        "currency": "USD",
        "method": "cash",
        "commissionPercent": 0.0,
        "deliveryFeePercent": 5.0,
        "isRefundable": False,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": None,
        "isActive": True,
        "displayOrder": 6,
        "iconUrl": None,
        "instructions": "Paga en efectivo (USD) al momento de la entrega.",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
]


async def migrate_payment_methods():
    """Migrate payment methods collection."""
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    collection = db.payment_methods

    print("Starting payment methods migration...")

    # Check if collection has documents
    count = await collection.count_documents({})
    print(f"Found {count} existing payment methods")

    if count == 0:
        # Insert initial payment methods
        print("Inserting initial payment methods...")
        result = await collection.insert_many(INITIAL_PAYMENT_METHODS)
        print(f"Inserted {len(result.inserted_ids)} payment methods")
    else:
        # Update existing documents with new fields
        print("Updating existing payment methods with new fields...")

        # Add missing fields with defaults
        default_fields = {
            "name": "",
            "code": "",
            "commissionPercent": 0.0,
            "deliveryFeePercent": 0.0,
            "isRefundable": True,
            "requiresProof": False,
            "requiresBusinessConfirmation": False,
            "expirationMinutes": None,
            "isActive": True,
            "displayOrder": 0,
            "iconUrl": None,
            "instructions": None,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }

        async for doc in collection.find({}):
            updates = {}
            for field, default_value in default_fields.items():
                if field not in doc:
                    updates[field] = default_value

            # Generate name and code from method if not present
            if "name" not in doc or not doc.get("name"):
                updates["name"] = f"{doc.get('method', 'Unknown')} {doc.get('currency', '')}"
            if "code" not in doc or not doc.get("code"):
                method = doc.get("method", "unknown").lower()
                currency = doc.get("currency", "").lower()
                updates["code"] = f"{method}_{currency}" if currency else method

            if updates:
                await collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": updates}
                )
                print(f"Updated payment method: {doc.get('_id')}")

    print("Payment methods migration completed!")
    client.close()


async def create_platform_document():
    """Create the platform document if it doesn't exist."""
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    collection = db.platform

    print("Checking platform document...")

    doc = await collection.find_one({"_id": "platform"})
    if not doc:
        print("Creating platform document...")
        platform_doc = {
            "_id": "platform",
            "name": "Llego",
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
            "totalCommissionsCollected": 0.0,
            "totalOrdersProcessed": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await collection.insert_one(platform_doc)
        print("Platform document created!")
    else:
        print("Platform document already exists")

    client.close()


async def create_indexes():
    """Create indexes for payment_attempts collection."""
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]

    print("Creating indexes...")

    # Payment attempts indexes
    payment_attempts = db.payment_attempts
    await payment_attempts.create_index("orderId")
    await payment_attempts.create_index("stripePaymentIntentId", sparse=True)
    await payment_attempts.create_index([("status", 1), ("expiresAt", 1)])
    await payment_attempts.create_index("createdAt")
    print("✓ Payment attempts indexes created")

    # Update orders collection with new index
    orders = db.orders
    await orders.create_index("currentPaymentAttemptId", sparse=True)
    print("✓ Orders index updated")

    client.close()


async def main():
    """Run all migrations."""
    await migrate_payment_methods()
    await create_platform_document()
    await create_indexes()
    print("\n✅ All migrations completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
