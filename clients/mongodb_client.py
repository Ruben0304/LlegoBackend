"""MongoDB client singleton."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

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
        await mongo_client.admin.command("ping")
        print(f"✓ Connected to MongoDB database: {settings.mongodb_database}")

        # Create indexes for error_logs collection
        await _create_error_logs_indexes()
        await _create_invitation_indexes()
        await _create_business_access_indexes()
        await _create_feed_indexes()
        await _create_user_indexes()
        await _create_ai_quota_indexes()
        await _create_delivery_zone_indexes()
        await _create_branch_delivery_request_indexes()
    except Exception as e:
        print(f"✗ Error connecting to MongoDB: {e}")
        raise


async def _create_error_logs_indexes():
    """Create indexes for error_logs collection to optimize duplicate detection."""
    try:
        error_logs_collection = database["error_logs"]

        # Compound index for finding similar pending errors
        await error_logs_collection.create_index(
            [("error_type", 1), ("error_message", 1), ("source", 1), ("resolved", 1)],
            name="idx_duplicate_detection",
            background=True,
        )

        # Index for cleanup queries (resolved errors by date)
        await error_logs_collection.create_index(
            [("resolved", 1), ("created_at", -1)],
            name="idx_resolved_created",
            background=True,
        )

        print("✓ Error logs indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create error_logs indexes: {e}")


async def _create_invitation_indexes():
    """Create indexes for branch_invitations collection."""
    try:
        invitations_collection = database["branch_invitations"]

        await invitations_collection.create_index(
            "code", unique=True, name="idx_code_unique", background=True
        )

        await invitations_collection.create_index(
            [("businessId", 1), ("status", 1), ("invitationType", 1)],
            name="idx_business_active",
            background=True,
        )

        await invitations_collection.create_index(
            "usedBy", name="idx_used_by", background=True
        )

        await invitations_collection.create_index(
            [("accessExpiresAt", 1), ("status", 1)],
            name="idx_access_expiration",
            background=True,
        )

        print("✓ Branch invitation indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create branch invitation indexes: {e}")


async def _create_business_access_indexes():
    """Create indexes for business_access collection."""
    try:
        access_collection = database["business_access"]

        await access_collection.create_index(
            [("userId", 1), ("businessId", 1), ("isActive", 1)],
            name="idx_user_business_active",
            background=True,
        )

        await access_collection.create_index(
            [("businessId", 1), ("isActive", 1)],
            name="idx_business_active",
            background=True,
        )

        await access_collection.create_index(
            [("expiresAt", 1), ("isActive", 1)],
            name="idx_expiration_cleanup",
            background=True,
        )

        await access_collection.create_index(
            "invitationId", name="idx_invitation", background=True
        )

        print("✓ Business access indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create business access indexes: {e}")


async def _create_feed_indexes():
    """Create indexes for feed system and branch likes."""
    try:
        # products: freshness y filtro por branch + disponibilidad
        products_collection = database["products"]

        await products_collection.create_index(
            [("createdAt", -1)], name="idx_products_created_at", background=True
        )

        await products_collection.create_index(
            [("branchId", 1), ("availability", 1)],
            name="idx_products_branch_availability",
            background=True,
        )

        await products_collection.create_index(
            [("categoryId", 1), ("branchId", 1)],
            name="idx_products_category_branch",
            background=True,
        )

        # favorites_cart: actividad reciente por tipo
        favorites_cart_collection = database["favorites_cart"]

        await favorites_cart_collection.create_index(
            [("type", 1), ("createdAt", -1)],
            name="idx_fav_type_created",
            background=True,
        )

        await favorites_cart_collection.create_index(
            [("userId", 1), ("type", 1)], name="idx_fav_user_type", background=True
        )

        # searches: actividad reciente global y por usuario
        searches_collection = database["searches"]

        await searches_collection.create_index(
            [("createdAt", -1)], name="idx_searches_created", background=True
        )

        await searches_collection.create_index(
            [("userId", 1), ("createdAt", -1)],
            name="idx_searches_user_created",
            background=True,
        )

        # branch_likes: unique por usuario+branch, popularidad, actividad
        branch_likes_collection = database["branch_likes"]

        await branch_likes_collection.create_index(
            [("userId", 1), ("branchId", 1)],
            name="idx_branch_likes_unique",
            unique=True,
            background=True,
        )

        await branch_likes_collection.create_index(
            [("branchId", 1)], name="idx_branch_likes_branch", background=True
        )

        await branch_likes_collection.create_index(
            [("createdAt", -1)], name="idx_branch_likes_created", background=True
        )

        print("✓ Feed indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create feed indexes: {e}")


async def _create_user_indexes():
    """Create text index on users collection for efficient search."""
    try:
        users_collection = database["users"]

        await users_collection.create_index(
            [("name", "text"), ("email", "text")],
            name="idx_users_text_search",
            default_language="spanish",
            background=True,
        )

        print("✓ User indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create user indexes: {e}")


async def _create_ai_quota_indexes():
    """Create indexes for AI quota usage collection."""
    try:
        usage_collection = database[settings.ai_usage_collection]

        await usage_collection.create_index(
            [("scope", 1), ("userId", 1), ("range", 1), ("periodKey", 1)],
            name="idx_ai_quota_user_period",
            background=True,
        )

        await usage_collection.create_index(
            [("scope", 1), ("userId", 1), ("deviceId", 1)],
            name="idx_ai_quota_user_device",
            background=True,
        )

        print("✓ AI quota indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create AI quota indexes: {e}")


async def _create_delivery_zone_indexes():
    """Create indexes for delivery_zones collection (H3 hexagonal zones)."""
    try:
        collection = database["delivery_zones"]

        # Unique index on h3Index — one zone per hexagon
        await collection.create_index(
            "h3Index",
            unique=True,
            name="idx_h3_index_unique",
            background=True,
        )

        # Lookup by city
        await collection.create_index(
            [("city", 1), ("isActive", 1)],
            name="idx_city_active",
            background=True,
        )

        # Lookup by province
        await collection.create_index(
            [("province", 1), ("isActive", 1)],
            name="idx_province_active",
            background=True,
        )

        # Active zones fast filter
        await collection.create_index(
            "isActive",
            name="idx_is_active",
            background=True,
        )

        print("✓ Delivery zone indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create delivery zone indexes: {e}")


async def _create_branch_delivery_request_indexes():
    """Create indexes for branch_delivery_requests collection."""
    try:
        collection = database["branch_delivery_requests"]

        await collection.create_index(
            [("deliveryPersonId", 1), ("branchId", 1)],
            unique=True,
            name="idx_delivery_person_branch_unique",
            background=True,
        )

        await collection.create_index(
            [("branchId", 1), ("status", 1)],
            name="idx_branch_status",
            background=True,
        )

        await collection.create_index(
            [("deliveryPersonId", 1), ("status", 1)],
            name="idx_delivery_person_status",
            background=True,
        )

        print("✓ Branch delivery request indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create branch delivery request indexes: {e}")


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
