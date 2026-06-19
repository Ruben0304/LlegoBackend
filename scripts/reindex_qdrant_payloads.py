"""Backfill enriched Qdrant payloads for existing points (no re-embedding).

Payload enrichment does not change the vectors, so this uses Qdrant's
`set_payload` (a cheap merge) instead of re-embedding every entity through
Gemini. It walks every point already in each collection, looks up the matching
MongoDB document, and writes the canonical enriched payload built by
`services.qdrant_payloads`.

Run once after deploying the payload-enrichment change:

    python scripts/reindex_qdrant_payloads.py

It is idempotent and safe to re-run.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients import (  # noqa: E402
    close_mongo_connection,
    close_qdrant_connection,
    connect_to_mongo,
    connect_to_qdrant,
    ensure_collections_and_indexes,
    get_qdrant_client,
)
from repositories import branches_repo, businesses_repo, products_repo  # noqa: E402
from services.qdrant_payloads import (  # noqa: E402
    branch_payload,
    business_payload,
    product_payload,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def _scroll_point_ids_by_mongo_id(collection_name: str) -> Dict[str, Any]:
    """Return {mongo_id: point_id} for every point in the collection."""
    qdrant_client = get_qdrant_client()
    mapping: Dict[str, Any] = {}
    offset = None

    while True:
        batch, offset = await qdrant_client.scroll(
            collection_name=collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not batch:
            break
        for point in batch:
            mongo_id = (point.payload or {}).get("mongo_id")
            if mongo_id:
                mapping[str(mongo_id)] = point.id
        if offset is None:
            break

    return mapping


async def backfill_collection(
    collection_name: str,
    fetch_all: Callable,
    payload_builder: Callable[[Any], Dict[str, Any]],
) -> Dict[str, int]:
    """Set enriched payloads for all points of one collection."""
    logger.info("=" * 60)
    logger.info("Collection: %s", collection_name)

    qdrant_client = get_qdrant_client()
    point_id_by_mongo = await _scroll_point_ids_by_mongo_id(collection_name)
    logger.info("  Points in Qdrant: %s", len(point_id_by_mongo))

    entities = await fetch_all()
    entities_by_id = {str(e.id): e for e in entities}
    logger.info("  Documents in Mongo: %s", len(entities_by_id))

    updated = 0
    missing_in_mongo = 0
    for mongo_id, point_id in point_id_by_mongo.items():
        entity = entities_by_id.get(mongo_id)
        if not entity:
            missing_in_mongo += 1
            continue
        try:
            await qdrant_client.set_payload(
                collection_name=collection_name,
                payload=payload_builder(entity),
                points=[point_id],
            )
            updated += 1
        except Exception as exc:  # pragma: no cover - operational logging
            logger.error("  set_payload failed for %s: %s", mongo_id, exc)

    logger.info(
        "  Summary -> updated=%s | orphan_points(no Mongo doc)=%s",
        updated,
        missing_in_mongo,
    )
    return {"updated": updated, "orphans": missing_in_mongo}


async def run() -> None:
    await connect_to_mongo()
    await connect_to_qdrant()
    await ensure_collections_and_indexes()

    try:
        await backfill_collection("products", products_repo.get_all, product_payload)
        await backfill_collection("branches", branches_repo.get_all, branch_payload)
        await backfill_collection("businesses", businesses_repo.get_all, business_payload)
    finally:
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(run())
