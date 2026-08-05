"""Recompute store price positioning (economica/promedio/cara) on demand.

For every store, compares its products against similar products from other stores
in the same category and labels the store by its median relative price. Writes
priceTier/priceIndex/priceConfidence onto each branch. The nightly lifespan
worker runs the same routine automatically; this is for running it manually.

    python scripts/recompute_price_positioning.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients import (  # noqa: E402
    close_mongo_connection,
    close_qdrant_connection,
    connect_to_mongo,
    connect_to_qdrant,
    ensure_collections_and_indexes,
)
from services.price_positioning_service import compute_price_positioning  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def run() -> None:
    await connect_to_mongo()
    await connect_to_qdrant()
    await ensure_collections_and_indexes()
    try:
        stats = await compute_price_positioning()
        logging.info("Done: %s", stats)
    finally:
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(run())
