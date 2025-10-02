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
    except Exception as e:
        print(f"✗ Error connecting to MongoDB: {e}")
        raise


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
