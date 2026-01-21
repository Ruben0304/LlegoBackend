"""
Auto-migration for payment methods and platform.
This runs automatically on server startup if needed.
"""
import logging
from datetime import datetime
from bson import ObjectId

from clients.mongodb_client import get_database

logger = logging.getLogger(__name__)


# Initial payment methods
INITIAL_PAYMENT_METHODS = [
    {
        "_id": "wallet_usd",
        "name": "Wallet USD",
        "code": "wallet_usd",
        "currency": "USD",
        "method": "wallet",
        "commissionPercent": 0.0,
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
        "_id": "wallet_cup",
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
        "_id": "stripe",
        "name": "Stripe (Tarjeta)",
        "code": "stripe",
        "currency": "USD",
        "method": "stripe",
        "commissionPercent": 3.5,
        "deliveryFeePercent": 0.0,
        "isRefundable": True,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": 30,
        "isActive": True,
        "displayOrder": 3,
        "iconUrl": None,
        "instructions": None,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": "transfermovil",
        "name": "Transfermóvil",
        "code": "transfermovil",
        "currency": "CUP",
        "method": "transfer",
        "commissionPercent": 2.0,
        "deliveryFeePercent": 0.0,
        "isRefundable": False,
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
        "_id": "cash",
        "name": "Efectivo",
        "code": "cash",
        "currency": "CUP",
        "method": "cash",
        "commissionPercent": 0.0,
        "deliveryFeePercent": 5.0,
        "isRefundable": False,
        "requiresProof": False,
        "requiresBusinessConfirmation": False,
        "expirationMinutes": None,
        "isActive": True,
        "displayOrder": 5,
        "iconUrl": None,
        "instructions": "Paga en efectivo al momento de la entrega.",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": "cash_usd",
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


async def auto_migrate_payments():
    """
    Auto-migrate payment methods and platform.
    Runs on server startup, only creates if doesn't exist.
    """
    try:
        db = get_database()
        
        # 1. Check and create payment methods
        payment_methods = db.payment_methods
        count = await payment_methods.count_documents({})
        
        if count == 0:
            logger.info("🔄 Creating initial payment methods...")
            await payment_methods.insert_many(INITIAL_PAYMENT_METHODS)
            logger.info(f"✅ Created {len(INITIAL_PAYMENT_METHODS)} payment methods")
        else:
            logger.info(f"✅ Payment methods already exist ({count} methods)")
        
        # 2. Check and create platform document
        platform = db.platform
        platform_doc = await platform.find_one({"_id": "platform"})
        
        if not platform_doc:
            logger.info("🔄 Creating platform document...")
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
            await platform.insert_one(platform_doc)
            logger.info("✅ Platform document created")
        else:
            logger.info("✅ Platform document already exists")
        
        # 3. Create indexes
        logger.info("🔄 Creating payment indexes...")
        
        # Payment attempts indexes
        payment_attempts = db.payment_attempts
        await payment_attempts.create_index("orderId")
        await payment_attempts.create_index("stripePaymentIntentId", sparse=True)
        await payment_attempts.create_index([("status", 1), ("expiresAt", 1)])
        await payment_attempts.create_index("createdAt")
        
        # Orders index
        orders = db.orders
        await orders.create_index("currentPaymentAttemptId", sparse=True)
        
        logger.info("✅ Payment indexes created")
        logger.info("🎉 Payment system migration completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error in payment migration: {e}")
        # Don't raise - let the server start anyway
