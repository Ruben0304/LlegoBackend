"""Sync businesses and branches from MongoDB into Qdrant and verify coverage."""

import asyncio
import logging
import uuid
from typing import Any, Dict, Iterable, List, Set

from qdrant_client.models import PointStruct

from clients import (
    close_mongo_connection,
    close_qdrant_connection,
    connect_to_mongo,
    connect_to_qdrant,
    ensure_collections_and_indexes,
    get_qdrant_client,
)
from repositories import branches_repo, businesses_repo
from services.embeddings.gemini_service import GeminiEmbeddingService
from services.qdrant_payloads import branch_payload, business_payload

# Deterministic UUID namespace — MUST match the repositories / indexing service
# so this reindex updates the same points instead of creating duplicates.
_UUID_NAMESPACE = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")


def _mongo_id_to_uuid(mongo_id: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, mongo_id))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def _get_qdrant_mongo_ids(collection_name: str) -> Set[str]:
    """Fetch all mongo_id values currently present in a Qdrant collection."""
    qdrant_client = get_qdrant_client()
    mongo_ids: Set[str] = set()
    offset = None

    while True:
        batch_points, offset = await qdrant_client.scroll(
            collection_name=collection_name,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not batch_points:
            break

        for point in batch_points:
            payload = point.payload or {}
            mongo_id = payload.get("mongo_id")
            if mongo_id:
                mongo_ids.add(str(mongo_id))

        if offset is None:
            break

    return mongo_ids


async def _upsert_points(collection_name: str, points: List[PointStruct]) -> None:
    """Upsert points in batches."""
    if not points:
        return

    qdrant_client = get_qdrant_client()
    batch_size = 100
    for idx in range(0, len(points), batch_size):
        await qdrant_client.upsert(
            collection_name=collection_name,
            points=points[idx : idx + batch_size],
        )


def _to_business_point(embedding_service: GeminiEmbeddingService, business: Any) -> PointStruct:
    text_to_embed = f"{business.name} {business.description or ''}"
    embedding = embedding_service.generate_embedding(text_to_embed)
    return PointStruct(
        id=_mongo_id_to_uuid(str(business.id)),
        vector=embedding,
        payload=business_payload(business),
    )


def _to_branch_point(embedding_service: GeminiEmbeddingService, branch: Any) -> PointStruct:
    tipos_str = " ".join(branch.tipos or [])
    text_to_embed = f"{branch.name} {tipos_str}"
    embedding = embedding_service.generate_embedding(text_to_embed)
    return PointStruct(
        id=_mongo_id_to_uuid(str(branch.id)),
        vector=embedding,
        payload=branch_payload(branch),
    )


def _string_ids(items: Iterable[Any]) -> Set[str]:
    return {str(item.id) for item in items}


async def sync_businesses_and_branches() -> None:
    """Sync both businesses and branches from Mongo into Qdrant and verify counts."""
    await connect_to_mongo()
    await connect_to_qdrant()
    await ensure_collections_and_indexes()

    try:
        embedding_service = GeminiEmbeddingService()

        businesses = await businesses_repo.get_all()
        branches = await branches_repo.get_all()

        logger.info("Mongo counts -> businesses=%s branches=%s", len(businesses), len(branches))

        business_points: List[PointStruct] = []
        branch_points: List[PointStruct] = []
        errors: Dict[str, int] = {"businesses": 0, "branches": 0}

        for business in businesses:
            try:
                business_points.append(_to_business_point(embedding_service, business))
            except Exception as exc:
                errors["businesses"] += 1
                logger.error("Error building business point for %s: %s", business.id, exc)

        for branch in branches:
            try:
                branch_points.append(_to_branch_point(embedding_service, branch))
            except Exception as exc:
                errors["branches"] += 1
                logger.error("Error building branch point for %s: %s", branch.id, exc)

        await _upsert_points("businesses", business_points)
        await _upsert_points("branches", branch_points)

        qdrant_business_ids = await _get_qdrant_mongo_ids("businesses")
        qdrant_branch_ids = await _get_qdrant_mongo_ids("branches")
        mongo_business_ids = _string_ids(businesses)
        mongo_branch_ids = _string_ids(branches)

        missing_business_ids = sorted(mongo_business_ids - qdrant_business_ids)
        missing_branch_ids = sorted(mongo_branch_ids - qdrant_branch_ids)

        logger.info(
            "Qdrant counts -> businesses=%s branches=%s",
            len(qdrant_business_ids),
            len(qdrant_branch_ids),
        )
        logger.info(
            "Sync summary -> upserted businesses=%s branches=%s | build_errors=%s",
            len(business_points),
            len(branch_points),
            errors,
        )

        if missing_business_ids:
            logger.error("Missing businesses in Qdrant (mongo_id): %s", missing_business_ids)
        else:
            logger.info("No missing businesses in Qdrant")

        if missing_branch_ids:
            logger.error("Missing branches in Qdrant (mongo_id): %s", missing_branch_ids)
        else:
            logger.info("No missing branches in Qdrant")

    finally:
        await close_mongo_connection()
        await close_qdrant_connection()


if __name__ == "__main__":
    asyncio.run(sync_businesses_and_branches())
