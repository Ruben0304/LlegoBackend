"""User taste vectors — the "recalculate once a day" recommendation job.

Instead of averaging a user's favourites/cart on every feed request, we keep a
persistent per-user *taste vector*: a weighted, time-decayed average of the
embeddings of everything they have interacted with (clicks, favourites, cart,
delivered orders). It is recomputed by a nightly worker and stored in the
``users`` Qdrant collection.

At request time "Especialmente para Ti" then does a single vector search against
this taste vector — cheap, and it captures the full decayed history rather than
just the last few favourites.

The product embeddings are *retrieved* from Qdrant (they are already stored), so
building a taste vector costs zero Gemini calls.
"""
import logging
import math
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from qdrant_client.http import models
from qdrant_client.models import PointStruct

from clients import get_database, get_qdrant_client

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"
PRODUCTS_COLLECTION = "products"

# Same namespace used everywhere else so ids stay consistent.
_UUID_NS = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")

# Cap how many of the user's strongest-intent products feed the vector — bounds
# the work and avoids diluting the taste with long-tail noise.
MAX_SOURCE_PRODUCTS = 60


def _user_point_id(user_id: str) -> str:
    return str(uuid.uuid5(_UUID_NS, str(user_id)))


def _weighted_average(weighted_vectors: List[Tuple[float, List[float]]]) -> Optional[List[float]]:
    """Weighted mean of vectors, L2-normalised. None if it can't be built."""
    if not weighted_vectors:
        return None
    dim = len(weighted_vectors[0][1])
    acc = [0.0] * dim
    total_w = 0.0
    for weight, vec in weighted_vectors:
        if weight <= 0 or len(vec) != dim:
            continue
        total_w += weight
        for i in range(dim):
            acc[i] += weight * vec[i]
    if total_w <= 0:
        return None
    acc = [x / total_w for x in acc]
    norm = math.sqrt(sum(x * x for x in acc))
    if norm == 0:
        return None
    return [x / norm for x in acc]


async def _fetch_product_vectors(product_ids: List[str]) -> Dict[str, List[float]]:
    """Retrieve stored product vectors by mongo_id (robust to id scheme)."""
    if not product_ids:
        return {}
    client = get_qdrant_client()
    vectors: Dict[str, List[float]] = {}
    flt = models.Filter(
        must=[models.FieldCondition(key="mongo_id", match=models.MatchAny(any=product_ids))]
    )
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=PRODUCTS_COLLECTION,
            scroll_filter=flt,
            with_payload=True,
            with_vectors=True,
            limit=256,
            offset=offset,
        )
        for point in points:
            mid = (point.payload or {}).get("mongo_id")
            if mid and point.vector is not None and str(mid) not in vectors:
                vectors[str(mid)] = list(point.vector)
        if offset is None or not points:
            break
    return vectors


async def build_user_taste_vector(user_id: str) -> Optional[Tuple[List[float], int]]:
    """Build (taste_vector, source_count) for a user, or None if no history."""
    # Reuse the feed's weighted/decayed intent map (lazy import avoids a cycle).
    from services.feed_service import feed_service

    profile = await feed_service._build_para_ti_user_profile(user_id)
    intent: Dict[str, float] = profile.get("product_intent") or {}
    if not intent:
        return None

    top = sorted(intent.items(), key=lambda kv: kv[1], reverse=True)[:MAX_SOURCE_PRODUCTS]
    product_ids = [pid for pid, _ in top]
    vec_by_id = await _fetch_product_vectors(product_ids)

    weighted = [(weight, vec_by_id[pid]) for pid, weight in top if pid in vec_by_id]
    vector = _weighted_average(weighted)
    if vector is None:
        return None
    return vector, len(weighted)


async def upsert_user_taste_vector(
    user_id: str, vector: List[float], source_count: int
) -> None:
    """Store/refresh the user's taste vector in the ``users`` collection."""
    client = get_qdrant_client()
    await client.upsert(
        collection_name=USERS_COLLECTION,
        points=[
            PointStruct(
                id=_user_point_id(user_id),
                vector=vector,
                payload={
                    "user_id": str(user_id),
                    "source_count": source_count,
                    "updatedAt": datetime.utcnow().isoformat(),
                },
            )
        ],
    )


async def get_user_taste_vector(user_id: str) -> Optional[List[float]]:
    """Retrieve a user's precomputed taste vector, or None if not available."""
    try:
        client = get_qdrant_client()
    except RuntimeError:
        return None
    try:
        points = await client.retrieve(
            collection_name=USERS_COLLECTION,
            ids=[_user_point_id(user_id)],
            with_vectors=True,
        )
        if points and points[0].vector is not None:
            return list(points[0].vector)
    except Exception as e:
        logger.debug(f"Could not retrieve taste vector for {user_id}: {e}")
    return None


async def _active_user_ids() -> List[str]:
    """Users worth recomputing: anyone with cart/favourite or order activity."""
    db = get_database()
    ids = set()
    try:
        for uid in await db["favorites_cart"].distinct("userId"):
            if uid is not None:
                ids.add(str(uid))
    except Exception as e:
        logger.warning(f"Could not list favorites_cart users: {e}")
    try:
        for cid in await db["orders"].distinct("customerId"):
            if cid is not None:
                ids.add(str(cid))
    except Exception as e:
        logger.warning(f"Could not list order customers: {e}")
    return list(ids)


async def recompute_all_taste_vectors() -> Dict[str, int]:
    """Rebuild taste vectors for all active users. Safe no-op if Qdrant is down."""
    try:
        get_qdrant_client()
    except RuntimeError:
        logger.warning("Qdrant unavailable — skipping taste vector recompute")
        return {"users": 0, "updated": 0, "skipped": 0}

    user_ids = await _active_user_ids()
    updated = 0
    skipped = 0
    for user_id in user_ids:
        try:
            built = await build_user_taste_vector(user_id)
            if not built:
                skipped += 1
                continue
            vector, source_count = built
            await upsert_user_taste_vector(user_id, vector, source_count)
            updated += 1
        except Exception as e:
            logger.error(f"Error building taste vector for {user_id}: {e}")
            skipped += 1

    logger.info(
        "Taste vectors recomputed: users=%s updated=%s skipped=%s",
        len(user_ids),
        updated,
        skipped,
    )
    return {"users": len(user_ids), "updated": updated, "skipped": skipped}
