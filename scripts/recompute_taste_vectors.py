"""Recompute per-user taste vectors on demand.

Builds a weighted, time-decayed taste vector for every active user (anyone with
cart/favourite or order activity) and stores it in the ``users`` Qdrant
collection. Used by "Especialmente para Ti". The nightly lifespan worker runs
the same routine automatically; this is for running it manually.

    python scripts/recompute_taste_vectors.py
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
from services.taste_vector_service import recompute_all_taste_vectors  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def run() -> None:
    await connect_to_mongo()
    await connect_to_qdrant()
    await ensure_collections_and_indexes()
    try:
        stats = await recompute_all_taste_vectors()
        logging.info("Done: %s", stats)
    finally:
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(run())
