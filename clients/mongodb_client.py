"""MongoDB client singleton."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from core.config import settings

# Global database instance
mongo_client: Optional[AsyncIOMotorClient] = None
database: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo():
    """Connect to MongoDB"""
    global mongo_client, database
    try:
        mongo_client = AsyncIOMotorClient(settings.mongodb_url)
        database = mongo_client[settings.mongodb_database]
        # Test connection
        await mongo_client.admin.command('ping')
        print(f"✓ Connected to MongoDB database: {settings.mongodb_database}")

        # Create indexes for error_logs collection
        await _create_error_logs_indexes()
    except Exception as e:
        print(f"✗ Error connecting to MongoDB: {e}")
        raise


async def _create_error_logs_indexes():
    """Create indexes for error_logs collection to optimize duplicate detection."""
    try:
        error_logs_collection = database["error_logs"]

        # Compound index for finding similar pending errors
        await error_logs_collection.create_index(
            [
                ("error_type", 1),
                ("error_message", 1),
                ("source", 1),
                ("resolved", 1)
            ],
            name="idx_duplicate_detection",
            background=True
        )

        # Index for cleanup queries (resolved errors by date)
        await error_logs_collection.create_index(
            [("resolved", 1), ("created_at", -1)],
            name="idx_resolved_created",
            background=True
        )

        print("✓ Error logs indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create error_logs indexes: {e}")


async def close_mongo_connection():
    """Close MongoDB connection"""
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("✓ MongoDB connection closed")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    if database is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() first.")
    return database
