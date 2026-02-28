"""Reindex businesses from MongoDB into Qdrant without deleting data."""

import asyncio
import logging

from clients import (
    close_mongo_connection,
    close_qdrant_connection,
    connect_to_mongo,
    connect_to_qdrant,
)
from repositories import businesses_repo

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def reindex_businesses() -> None:
    await connect_to_mongo()
    await connect_to_qdrant()

    try:
        businesses = await businesses_repo.get_all()
        if not businesses:
            logger.info("No businesses found in MongoDB to reindex.")
            return

        reindexed = 0
        errors = 0
        for business in businesses:
            try:
                await businesses_repo._upsert_to_qdrant(business)
                reindexed += 1
            except Exception as exc:
                errors += 1
                logger.error("Error reindexing business %s: %s", business.id, exc)

        logger.info("Business reindex finished. reindexed=%s errors=%s", reindexed, errors)
    finally:
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(reindex_businesses())
