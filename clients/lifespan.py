"""FastAPI lifespan context manager for all clients."""
from contextlib import asynccontextmanager
import asyncio
import logging
from clients.mongodb_client import connect_to_mongo, close_mongo_connection
from clients.qdrant_client import connect_to_qdrant, close_qdrant_connection
from clients.gemini_client import connect_to_gemini, close_gemini_connection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan context manager.

    Initializes all client connections on startup and closes them on shutdown.
    """
    # Startup: Initialize all clients
    logger.info("🚀 Starting application...")
    print("🚀 Starting application...")

    logger.info("Connecting to MongoDB...")
    await connect_to_mongo()
    logger.info("✓ MongoDB connected")

    logger.info("Connecting to Qdrant...")
    await connect_to_qdrant()
    logger.info("✓ Qdrant connected")

    logger.info("Connecting to Gemini...")
    connect_to_gemini()
    logger.info("✓ Gemini connected")

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
                logger.info("Access expiration worker sleeping for 15 minutes...")
                await asyncio.sleep(900)

        logger.info("Starting access expiration worker...")
        asyncio.create_task(run_expiration_worker())
        logger.info("✓ Access expiration worker task created")
    except Exception as e:
        logger.error(f"⚠ Warning: Could not start access expiration worker: {e}")
        print(f"⚠ Warning: Could not start access expiration worker: {e}")

    logger.info("✓ All clients initialized successfully")
    print("✓ All clients initialized successfully\n")

    logger.info("Application ready to receive requests")

    yield

    # Shutdown: Close all connections
    logger.info("🛑 Shutting down application...")
    print("\n🛑 Shutting down application...")

    logger.info("Closing MongoDB connection...")
    await close_mongo_connection()
    logger.info("✓ MongoDB closed")

    logger.info("Closing Qdrant connection...")
    await close_qdrant_connection()
    logger.info("✓ Qdrant closed")

    logger.info("Closing Gemini connection...")
    close_gemini_connection()
    logger.info("✓ Gemini closed")

    logger.info("✓ All clients closed successfully")
    print("✓ All clients closed successfully")
