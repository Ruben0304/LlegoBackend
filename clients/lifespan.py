"""FastAPI lifespan context manager for all clients."""
from contextlib import asynccontextmanager
from clients.mongodb_client import connect_to_mongo, close_mongo_connection
from clients.qdrant_client import connect_to_qdrant, close_qdrant_connection
from clients.gemini_client import connect_to_gemini, close_gemini_connection


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan context manager.

    Initializes all client connections on startup and closes them on shutdown.
    """
    # Startup: Initialize all clients
    print("🚀 Starting application...")
    await connect_to_mongo()
    await connect_to_qdrant()
    connect_to_gemini()
    
    # Create order indexes
    try:
        from orders.repository import create_order_indexes
        await create_order_indexes()
    except Exception as e:
        print(f"⚠ Warning: Could not create order indexes: {e}")
    
    print("✓ All clients initialized successfully\n")

    yield

    # Shutdown: Close all connections
    print("\n🛑 Shutting down application...")
    await close_mongo_connection()
    await close_qdrant_connection()
    close_gemini_connection()
    print("✓ All clients closed successfully")
