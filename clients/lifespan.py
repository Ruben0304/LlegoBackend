"""FastAPI lifespan context manager for all clients."""

import asyncio
import logging
from contextlib import asynccontextmanager

from clients.gemini_client import close_gemini_connection, connect_to_gemini
from clients.mongodb_client import close_mongo_connection, connect_to_mongo
from clients.qdrant_client import close_qdrant_connection, connect_to_qdrant

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan context manager.

    Initializes all client connections on startup and closes them on shutdown.
    """
    logger.info("Starting application...")
    print("Starting application...")

    logger.info("Connecting to MongoDB...")
    await connect_to_mongo()
    logger.info("MongoDB connected")

    logger.info("Connecting to Qdrant...")
    await connect_to_qdrant()
    logger.info("Qdrant connected")

    logger.info("Connecting to Gemini...")
    connect_to_gemini()
    logger.info("Gemini connected")

    background_tasks = []

    try:
        from services.access_expiration_worker import expire_old_accesses

        async def run_access_expiration_worker():
            """Background task that runs every 15 minutes to expire old access."""
            while True:
                try:
                    logger.info("Running access expiration worker...")
                    await expire_old_accesses()
                    logger.info("Access expiration worker completed successfully")
                except Exception as e:
                    logger.error(f"Error in access expiration worker: {e}", exc_info=True)

                await asyncio.sleep(900)

        logger.info("Starting access expiration worker...")
        background_tasks.append(asyncio.create_task(run_access_expiration_worker()))
        logger.info("Access expiration worker task created")
    except Exception as e:
        logger.error(f"Warning: Could not start access expiration worker: {e}")
        print(f"Warning: Could not start access expiration worker: {e}")

    try:
        from services.order_timeout_worker import expire_order_deadlines

        async def run_order_timeout_worker():
            """Background task that checks order SLA deadlines every 60 seconds."""
            while True:
                try:
                    logger.info("Running order timeout worker...")
                    expired = await expire_order_deadlines(limit=200)
                    if expired:
                        logger.info(
                            f"Order timeout worker cancelled {expired} stale orders"
                        )
                except Exception as e:
                    logger.error(f"Error in order timeout worker: {e}", exc_info=True)

                await asyncio.sleep(60)

        logger.info("Starting order timeout worker...")
        background_tasks.append(asyncio.create_task(run_order_timeout_worker()))
        logger.info("Order timeout worker task created")
    except Exception as e:
        logger.error(f"Warning: Could not start order timeout worker: {e}")
        print(f"Warning: Could not start order timeout worker: {e}")

    try:
        from services.account_deletion_worker import delete_expired_accounts

        async def run_account_deletion_worker():
            """Background task that hard-deletes accounts past their 30-day grace period (Apple Guideline 5.1.1(v)). Runs every 24h."""
            while True:
                try:
                    logger.info("Running account deletion worker...")
                    removed = await delete_expired_accounts()
                    if removed:
                        logger.info(
                            f"Account deletion worker removed {removed} expired account(s)"
                        )
                except Exception as e:
                    logger.error(f"Error in account deletion worker: {e}", exc_info=True)

                await asyncio.sleep(86400)

        logger.info("Starting account deletion worker...")
        background_tasks.append(asyncio.create_task(run_account_deletion_worker()))
        logger.info("Account deletion worker task created")
    except Exception as e:
        logger.error(f"Warning: Could not start account deletion worker: {e}")
        print(f"Warning: Could not start account deletion worker: {e}")

    # Seed the vehicles catalog (idempotent — skips if records already exist)
    try:
        from repositories.vehicle_repository import VehicleRepository
        from domain.orders import VehicleType
        repo = VehicleRepository()
        await repo.upsert_seed("Bicicleta", VehicleType.BICICLETA)
        await repo.upsert_seed("Triciclo",  VehicleType.TRICICLO)
        logger.info("Vehicles catalog seeded")
    except Exception as e:
        logger.warning(f"Could not seed vehicles catalog: {e}")

    logger.info("All clients initialized successfully")
    print("All clients initialized successfully\n")

    logger.info("Application ready to receive requests")

    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)

        logger.info("Shutting down application...")
        print("\nShutting down application...")

        logger.info("Closing MongoDB connection...")
        await close_mongo_connection()
        logger.info("MongoDB closed")

        logger.info("Closing Qdrant connection...")
        await close_qdrant_connection()
        logger.info("Qdrant closed")

        logger.info("Closing Gemini connection...")
        close_gemini_connection()
        logger.info("Gemini closed")

        logger.info("All clients closed successfully")
        print("All clients closed successfully")
