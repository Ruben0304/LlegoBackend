"""Script to create MongoDB indexes for orders system."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings


async def create_indexes():
    """Create all required indexes for the orders system."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    
    print("Creating indexes for orders system...")
    
    # Orders collection
    print("\n📦 Orders collection:")
    await db.orders.create_index([("customerId", 1), ("createdAt", -1)])
    print("  ✓ customerId + createdAt")
    
    await db.orders.create_index([("branchId", 1), ("status", 1), ("createdAt", -1)])
    print("  ✓ branchId + status + createdAt")
    
    await db.orders.create_index("orderNumber", unique=True)
    print("  ✓ orderNumber (unique)")
    
    await db.orders.create_index("status")
    print("  ✓ status")
    
    await db.orders.create_index([("deliveryAddress.coordinates", "2dsphere")])
    print("  ✓ deliveryAddress.coordinates (2dsphere)")
    
    await db.orders.create_index([("paymentStatus", 1), ("status", 1)])
    print("  ✓ paymentStatus + status")
    
    # Delivery persons collection
    print("\n🛵 Delivery persons collection:")
    await db.delivery_persons.create_index([("currentLocation", "2dsphere")])
    print("  ✓ currentLocation (2dsphere)")
    
    await db.delivery_persons.create_index([("isActive", 1), ("isOnline", 1)])
    print("  ✓ isActive + isOnline")
    
    await db.delivery_persons.create_index("userId", unique=True)
    print("  ✓ userId (unique)")
    
    # Order location updates collection (with TTL)
    print("\n📍 Order location updates collection:")
    await db.order_location_updates.create_index("orderId")
    print("  ✓ orderId")
    
    await db.order_location_updates.create_index(
        "timestamp", 
        expireAfterSeconds=86400
    )
    print("  ✓ timestamp (TTL: 24 hours)")
    
    print("\n✅ All indexes created successfully!")
    client.close()


if __name__ == "__main__":
    asyncio.run(create_indexes())
