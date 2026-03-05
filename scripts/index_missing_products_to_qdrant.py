"""
Script to index MongoDB documents missing from Qdrant (products, branches, businesses).

Fetches all documents from MongoDB, checks which ones are already in Qdrant
(by mongo_id in payload), and indexes only the missing ones.

Usage:
    python scripts/index_missing_products_to_qdrant.py
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Set

from qdrant_client.models import PointStruct

from clients.mongodb_client import connect_to_mongo, close_mongo_connection, get_database
from clients.qdrant_client import connect_to_qdrant, close_qdrant_connection, get_qdrant_client
from clients.gemini_client import connect_to_gemini, close_gemini_connection
from services.embeddings.gemini_service import GeminiEmbeddingService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 10          # Documents per Gemini batch
DELAY_BETWEEN_BATCHES = 1.0  # seconds, to respect Gemini rate limits

# Namespace for deterministic UUID generation from MongoDB ObjectIds
_UUID_NAMESPACE = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")

# Collection configs: qdrant_name, mongo_name, mongo_fields, text_fn, payload_fn
COLLECTIONS = [
    {
        "label": "products",
        "qdrant": "products",
        "mongo": "products",
        "fields": {"_id": 1, "name": 1, "description": 1, "price": 1},
        "text": lambda d: f"{d.get('name', '')} {d.get('description', '') or ''}".strip(),
        "payload": lambda d, mid: {
            "mongo_id": mid,
            "name": d.get("name", ""),
            "price": d.get("price"),
            "description": d.get("description") or "",
        },
    },
    {
        "label": "branches",
        "qdrant": "branches",
        "mongo": "branches",
        "fields": {"_id": 1, "name": 1, "tipos": 1, "address": 1},
        "text": lambda d: (
            f"{d.get('name', '')}. "
            f"Tipos: {', '.join(d.get('tipos') or [])}. "
            f"{d.get('address', '') or ''}"
        ).strip(),
        "payload": lambda d, mid: {
            "mongo_id": mid,
            "name": d.get("name", ""),
            "tipos": d.get("tipos") or [],
        },
    },
    {
        "label": "businesses",
        "qdrant": "businesses",
        "mongo": "bussisnes",  # intentional typo — kept for compatibility
        "fields": {"_id": 1, "name": 1, "description": 1},
        "text": lambda d: f"{d.get('name', '')}. {d.get('description', '') or ''}".strip(),
        "payload": lambda d, mid: {
            "mongo_id": mid,
            "name": d.get("name", ""),
            "description": d.get("description") or "",
        },
    },
]


def mongo_id_to_uuid(mongo_id: str) -> str:
    """Convert a MongoDB ObjectId string to a deterministic UUID."""
    return str(uuid.uuid5(_UUID_NAMESPACE, mongo_id))


async def get_indexed_mongo_ids(qdrant_client, qdrant_collection: str) -> Set[str]:
    """Return the set of mongo_ids already present in a Qdrant collection."""
    mongo_ids: Set[str] = set()
    offset = None

    while True:
        result = await qdrant_client.scroll(
            collection_name=qdrant_collection,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        batch, offset = result
        if not batch:
            break
        for point in batch:
            mid = point.payload.get("mongo_id")
            if mid:
                mongo_ids.add(mid)
        if offset is None:
            break

    return mongo_ids


async def index_collection(
    db,
    qdrant_client,
    embedding_service: GeminiEmbeddingService,
    config: Dict[str, Any],
) -> Dict[str, int]:
    label = config["label"]
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Collection: {label}")
    logger.info(f"{'=' * 60}")

    # Load from MongoDB
    cursor = db[config["mongo"]].find({}, config["fields"])
    documents = await cursor.to_list(length=None)
    logger.info(f"  MongoDB documents: {len(documents)}")

    # Get already-indexed ids
    indexed_ids = await get_indexed_mongo_ids(qdrant_client, config["qdrant"])
    logger.info(f"  Already in Qdrant:  {len(indexed_ids)}")

    missing = [d for d in documents if str(d["_id"]) not in indexed_ids]
    logger.info(f"  Missing:            {len(missing)}")

    if not missing:
        logger.info("  → Nothing to index.")
        return {"indexed": 0, "errors": 0, "total": 0}

    total = len(missing)
    indexed = 0
    errors = 0

    for i in range(0, total, BATCH_SIZE):
        batch = missing[i: i + BATCH_SIZE]
        texts = [config["text"](doc) for doc in batch]

        try:
            embeddings = embedding_service.generate_embeddings_batch(
                texts, task_type="RETRIEVAL_DOCUMENT"
            )
        except Exception as e:
            logger.error(f"  Gemini error on batch {i // BATCH_SIZE + 1}: {e}")
            errors += len(batch)
            time.sleep(DELAY_BETWEEN_BATCHES * 3)
            continue

        points = []
        for doc, embedding in zip(batch, embeddings):
            mongo_id = str(doc["_id"])
            points.append(
                PointStruct(
                    id=mongo_id_to_uuid(mongo_id),
                    vector=embedding,
                    payload=config["payload"](doc, mongo_id),
                )
            )

        try:
            await qdrant_client.upsert(collection_name=config["qdrant"], points=points)
            indexed += len(points)
            logger.info(
                f"  Batch {i // BATCH_SIZE + 1}: indexed {len(points)} ({indexed}/{total})"
            )
        except Exception as e:
            logger.error(f"  Qdrant upsert error on batch {i // BATCH_SIZE + 1}: {e}")
            errors += len(batch)

        if i + BATCH_SIZE < total:
            time.sleep(DELAY_BETWEEN_BATCHES)

    return {"indexed": indexed, "errors": errors, "total": total}


async def run():
    logger.info("=" * 60)
    logger.info("Starting: index missing documents → Qdrant")
    logger.info("=" * 60)

    await connect_to_mongo()
    await connect_to_qdrant()
    connect_to_gemini()

    try:
        db = get_database()
        qdrant_client = get_qdrant_client()
        embedding_service = GeminiEmbeddingService()

        total_indexed = 0
        total_errors = 0

        for config in COLLECTIONS:
            stats = await index_collection(db, qdrant_client, embedding_service, config)
            total_indexed += stats["indexed"]
            total_errors += stats["errors"]

        logger.info(f"\n{'=' * 60}")
        logger.info(f"TOTAL — Indexed: {total_indexed}  |  Errors: {total_errors}")
        logger.info("=" * 60)

    finally:
        close_gemini_connection()
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(run())
