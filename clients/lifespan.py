"""FastAPI lifespan context manager for all clients."""
from contextlib import asynccontextmanager
import asyncio
import logging
from clients.mongodb_client import connect_to_mongo, close_mongo_connection
from clients.qdrant_client import connect_to_qdrant, close_qdrant_connection
from clients.gemini_client import connect_to_gemini, close_gemini_connection
from scripts.cleanup_qdrant_duplicates import cleanup_qdrant_duplicates_on_startup

logger = logging.getLogger(__name__)


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

    # Cleanup duplicated points in Qdrant collections on startup
    await cleanup_qdrant_duplicates_on_startup()

    # Start access expiration worker
    try:
        from services.access_expiration_worker import expire_old_accesses
        
        async def run_expiration_worker():
            """Background task that runs every 15 minutes to expire old access."""
            while True:
                try:
                    logger.info("Running access expiration worker...")
                    await expire_old_accesses()
                    logger.info("Access expiration worker completed successfully")
                except Exception as e:
                    logger.error(f"Error in access expiration worker: {e}", exc_info=True)
                
                # Wait 15 minutes before next run
                await asyncio.sleep(900)
        
        logger.info("Starting access expiration worker...")
        asyncio.create_task(run_expiration_worker())
    except Exception as e:
        print(f"⚠ Warning: Could not start access expiration worker: {e}")

    print("✓ All clients initialized successfully\n")

    yield

    # Shutdown: Close all connections
    print("\n🛑 Shutting down application...")
    await close_mongo_connection()
    await close_qdrant_connection()
    close_gemini_connection()
    print("✓ All clients closed successfully")
