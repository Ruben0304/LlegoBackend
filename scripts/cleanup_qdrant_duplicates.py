"""Cleanup duplicated points in Qdrant collections safely by mongo_id."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client.http import models as qdrant_models

from clients.qdrant_client import (
    close_qdrant_connection,
    connect_to_qdrant,
    get_qdrant_client,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DedupRule:
    collection_name: str
    key_fields: Tuple[str, ...]


DEDUP_RULES: Tuple[DedupRule, ...] = (
    # Deduplicate only same MongoDB entity to avoid deleting valid records
    # that can share name/price across different businesses/branches/products.
    DedupRule(collection_name="products", key_fields=("mongo_id",)),
    DedupRule(collection_name="branches", key_fields=("mongo_id",)),
    DedupRule(collection_name="businesses", key_fields=("mongo_id",)),
)


def _normalize_value(value: Any) -> Any:
    """Normalize values used for duplicate keys."""
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _build_group_key(payload: Dict[str, Any], key_fields: Tuple[str, ...]) -> Optional[Tuple[Any, ...]]:
    key_values: List[Any] = []
    for field in key_fields:
        value = payload.get(field)
        if value is None:
            return None
        key_values.append(_normalize_value(value))
    return tuple(key_values)


async def _get_all_points(collection_name: str) -> List[Any]:
    """Fetch all points from a Qdrant collection."""
    qdrant_client = get_qdrant_client()
    points: List[Any] = []
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
        points.extend(batch_points)
        if offset is None:
            break

    return points


def _select_point_to_keep(points: List[Any]) -> Any:
    """Choose one point to keep from a duplicate group."""
    # Prefer deterministic IDs (point.id == mongo_id)
    for point in points:
        payload = point.payload or {}
        mongo_id = str(payload.get("mongo_id") or "")
        if mongo_id and str(point.id) == mongo_id:
            return point

    # Then prefer points that at least have mongo_id
    for point in points:
        payload = point.payload or {}
        if payload.get("mongo_id"):
            return point

    # Fallback to first one
    return points[0]


async def _delete_points(collection_name: str, point_ids: List[Any]) -> int:
    """Delete points from Qdrant in batches."""
    if not point_ids:
        return 0

    qdrant_client = get_qdrant_client()
    deleted = 0
    batch_size = 100

    for index in range(0, len(point_ids), batch_size):
        batch = point_ids[index : index + batch_size]
        await qdrant_client.delete(
            collection_name=collection_name,
            points_selector=qdrant_models.PointIdsList(points=batch),
        )
        deleted += len(batch)

    return deleted


async def deduplicate_collection(rule: DedupRule) -> Dict[str, int]:
    """Deduplicate one Qdrant collection according to the configured key fields."""
    points = await _get_all_points(rule.collection_name)
    groups: Dict[Tuple[Any, ...], List[Any]] = {}

    for point in points:
        payload = point.payload or {}
        group_key = _build_group_key(payload, rule.key_fields)
        if group_key is None:
            continue
        groups.setdefault(group_key, []).append(point)

    duplicate_group_count = 0
    point_ids_to_delete: List[Any] = []

    for grouped_points in groups.values():
        if len(grouped_points) <= 1:
            continue
        duplicate_group_count += 1
        keep_point = _select_point_to_keep(grouped_points)

        for point in grouped_points:
            if point.id != keep_point.id:
                point_ids_to_delete.append(point.id)

    deleted_points = await _delete_points(rule.collection_name, point_ids_to_delete)
    return {
        "total_points": len(points),
        "duplicate_groups": duplicate_group_count,
        "deleted_points": deleted_points,
    }


async def cleanup_qdrant_duplicates_on_startup() -> None:
    """Run duplicate cleanup for products, branches, and businesses."""
    try:
        get_qdrant_client()
    except RuntimeError:
        logger.warning("Qdrant client not available, skipping duplicate cleanup")
        return

    logger.info("[Qdrant] Starting duplicate cleanup on startup")
    total_deleted = 0

    for rule in DEDUP_RULES:
        try:
            result = await deduplicate_collection(rule)
            total_deleted += result["deleted_points"]
            logger.info(
                "[Qdrant] %s: points=%s, duplicate_groups=%s, deleted=%s",
                rule.collection_name,
                result["total_points"],
                result["duplicate_groups"],
                result["deleted_points"],
            )
        except Exception as exc:
            logger.error(
                "[Qdrant] Error deduplicating collection '%s': %s",
                rule.collection_name,
                exc,
                exc_info=True,
            )

    logger.info("[Qdrant] Duplicate cleanup finished, total deleted=%s", total_deleted)


async def _run_standalone() -> None:
    """Allow running this script manually."""
    await connect_to_qdrant()
    try:
        await cleanup_qdrant_duplicates_on_startup()
    finally:
        await close_qdrant_connection()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_standalone())
