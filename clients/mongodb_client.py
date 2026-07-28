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
        mongo_client = AsyncIOMotorClient(
            settings.mongodb_url,
            maxPoolSize=150,
            minPoolSize=20,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            retryWrites=True,
        )
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
        await _create_ai_chat_indexes()
        await _create_ai_quota_indexes()
        await _create_delivery_zone_indexes()
        await _create_branch_delivery_request_indexes()
        await _create_crypto_payment_indexes()
        await _create_search_perf_indexes()
        await _create_order_indexes()
        await _create_branch_indexes()
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


async def _create_ai_chat_indexes():
    """Indexes for the AI assistant chat (memory + keyword retrieval)."""
    try:
        # chat_messages: the assistant reads the last N messages of a session on
        # every turn. Without this it's a collection scan plus an in-memory sort,
        # twice per message, on a collection that only grows.
        chat_collection = database["chat_messages"]

        await chat_collection.create_index(
            [("sessionId", 1), ("createdAt", -1)],
            name="idx_chat_session_created",
            background=True,
        )

        # products / branches: the chat's keyword leg used an unanchored
        # case-insensitive $regex, which can never use an index. These let it run
        # a $text search instead (it still falls back to the regex when $text
        # finds nothing, so partial words keep working).
        await database["products"].create_index(
            [("name", "text")],
            name="idx_products_text_search",
            default_language="spanish",
            background=True,
        )

        await database["branches"].create_index(
            [("name", "text")],
            name="idx_branches_text_search",
            default_language="spanish",
            background=True,
        )

        print("✓ AI chat indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create AI chat indexes: {e}")


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


async def _create_crypto_payment_indexes():
    """Create indexes for QvaPay, TronDealer and PendingPayout collections."""
    try:
        # qvapay_invoices — transactionUuid is the idempotency key
        qvapay_col = database["qvapay_invoices"]
        await qvapay_col.create_index(
            "transactionUuid",
            unique=True,
            name="idx_qvapay_transaction_uuid_unique",
            background=True,
        )
        await qvapay_col.create_index(
            "orderId",
            name="idx_qvapay_order_id",
            background=True,
        )
        await qvapay_col.create_index(
            [("status", 1), ("createdAt", 1)],
            name="idx_qvapay_status_created",
            background=True,
        )

        # trondealer_wallets — address is the webhook routing key
        td_col = database["trondealer_wallets"]
        await td_col.create_index(
            "address",
            unique=True,
            name="idx_trondealer_address_unique",
            background=True,
        )
        await td_col.create_index(
            "orderId",
            name="idx_trondealer_order_id",
            background=True,
        )
        await td_col.create_index(
            [("status", 1), ("createdAt", 1)],
            name="idx_trondealer_status_created",
            background=True,
        )

        # pending_payouts — admin liquidation queue
        payouts_col = database["pending_payouts"]
        await payouts_col.create_index(
            [("payoutStatus", 1), ("createdAt", 1)],
            name="idx_payouts_status_created",
            background=True,
        )
        await payouts_col.create_index(
            [("gateway", 1), ("payoutStatus", 1)],
            name="idx_payouts_gateway_status",
            background=True,
        )
        await payouts_col.create_index(
            "orderId",
            name="idx_payouts_order_id",
            background=True,
        )

        print("✓ Crypto payment indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create crypto payment indexes: {e}")


async def _create_search_perf_indexes():
    """Create indexes that back filter/search queries which otherwise full-scan.

    These complement the existing feed indexes and target queries that grow
    linearly with collection size (availability filters, regex lookups, search).
    """
    try:
        await database["products"].create_index(
            [("availability", 1)],
            name="idx_products_availability",
            background=True,
        )

        await database["branches"].create_index(
            [("tipos", 1)],
            name="idx_branches_tipos",
            background=True,
        )

        await database["payment_methods"].create_index(
            [("code", 1)],
            name="idx_payment_methods_code",
            background=True,
        )

        await database["tutorials"].create_index(
            [("title", "text"), ("description", "text"), ("tags", "text")],
            name="idx_tutorials_text_search",
            default_language="spanish",
            background=True,
        )

        print("✓ Search performance indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create search performance indexes: {e}")


async def _create_order_indexes():
    """Create indexes for orders and delivery collections."""
    try:
        orders = database["orders"]

        await orders.create_index(
            [("customerId", 1), ("createdAt", -1)],
            name="idx_orders_customer_date",
            background=True,
        )
        await orders.create_index(
            [("branchId", 1), ("status", 1), ("createdAt", -1)],
            name="idx_orders_branch_status_date",
            background=True,
        )
        await orders.create_index(
            [("businessId", 1), ("createdAt", -1)],
            name="idx_orders_business_date",
            background=True,
        )
        await orders.create_index(
            "orderNumber",
            unique=True,
            name="idx_orders_order_number_unique",
            background=True,
        )
        await orders.create_index(
            "status",
            name="idx_orders_status",
            background=True,
        )
        await orders.create_index(
            [("paymentStatus", 1), ("status", 1)],
            name="idx_orders_payment_status",
            background=True,
        )
        await orders.create_index(
            [("status", 1), ("deadlineAt", 1)],
            name="idx_orders_status_deadline",
            background=True,
        )
        await orders.create_index(
            [("status", 1), ("deliveryPersonId", 1), ("branchH3", 1)],
            name="idx_orders_status_dp_h3",
            background=True,
        )
        await orders.create_index(
            [("deliveryPersonId", 1), ("completedAt", -1), ("_id", -1)],
            name="idx_orders_dp_completed",
            background=True,
        )

        delivery_persons = database["delivery_persons"]

        await delivery_persons.create_index(
            [("isActive", 1), ("isOnline", 1)],
            name="idx_dp_active_online",
            background=True,
        )
        await delivery_persons.create_index(
            "userId",
            unique=True,
            name="idx_dp_user_id_unique",
            background=True,
        )

        order_locations = database["order_location_updates"]
        await order_locations.create_index("orderId", name="idx_oloc_order_id", background=True)
        await order_locations.create_index(
            "timestamp",
            name="idx_oloc_timestamp_ttl",
            expireAfterSeconds=86400,
            background=True,
        )

        print("✓ Order indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create order indexes: {e}")


async def _create_branch_indexes():
    """Create indexes for branches collection."""
    try:
        branches = database["branches"]

        await branches.create_index(
            [("businessId", 1)],
            name="idx_branches_business_id",
            background=True,
        )
        await branches.create_index(
            [("businessId", 1), ("isActive", 1)],
            name="idx_branches_business_active",
            background=True,
        )

        print("✓ Branch indexes created/verified")
    except Exception as e:
        print(f"⚠ Warning: Could not create branch indexes: {e}")


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
