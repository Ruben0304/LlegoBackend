"""Store price positioning within its niche (nightly job).

For each product we pull the most similar products from OTHER stores in the SAME
category (its niche) and compare prices. A product's *relative price* is its
price divided by the median price of those similar products (>1 pricier, <1
cheaper than the market for that item). A store's *price index* is the median of
its products' relative prices, and it is labelled economica / promedio / cara
from that index.

Why this beats a naive "more expensive in every case → expensive":
- median (not "in every case") resists a single weird competitor.
- prices are normalised to a base currency (USD) so CUP vs USD stores aren't
  falsely flagged.
- products with too few comparable neighbours are skipped, and a store needs a
  minimum number of judged products, so the verdict is backed by real signal.

Reuses everything from the recommender work: stored product vectors, the enriched
payload (categoryId/branchId/price/currency/availability) for server-side
filtering, and the nightly worker pattern. Zero new Gemini calls.
"""
import logging
import statistics
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from qdrant_client.http import models
from qdrant_client.models import RecommendInput, RecommendQuery, RecommendStrategy

from clients import get_database, get_qdrant_client
from utils.cache import invalidate_branch_cache

logger = logging.getLogger(__name__)

_UUID_NS = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")

NEIGHBOR_K = 20             # similar products to pull per product
MIN_NEIGHBORS = 3          # below this we can't judge a product's relative price
MIN_PRODUCTS_PER_BRANCH = 3  # below this we can't judge a store
CARA_THRESHOLD = 1.10      # index >= => cara
ECONOMICA_THRESHOLD = 0.90  # index <= => economica


def _product_uuid(product_id: str) -> str:
    return str(uuid.uuid5(_UUID_NS, str(product_id)))


def _oid(value: Any) -> Any:
    try:
        return ObjectId(str(value))
    except Exception:
        return value


def _to_usd(price: Any, currency: Any, exchange_rate: Any) -> Optional[float]:
    """Normalise a price to USD. None if it can't be normalised."""
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    cur = (currency or "USD").upper()
    if cur == "CUP":
        if not exchange_rate or float(exchange_rate) <= 0:
            return None
        return p / float(exchange_rate)
    return p  # USD (or unknown → assume USD baseline)


def _classify(index: float) -> str:
    if index >= CARA_THRESHOLD:
        return "cara"
    if index <= ECONOMICA_THRESHOLD:
        return "economica"
    return "promedio"


async def _branch_currency_map(db) -> Dict[str, Dict[str, Any]]:
    """branchId -> {exchangeRate} for currency normalisation."""
    out: Dict[str, Dict[str, Any]] = {}
    docs = await db["branches"].find(
        {}, {"_id": 1, "exchangeRate": 1, "acceptedCurrency": 1}
    ).to_list(length=None)
    for b in docs:
        out[str(b["_id"])] = {
            "exchangeRate": b.get("exchangeRate"),
            "acceptedCurrency": b.get("acceptedCurrency"),
        }
    return out


async def _relative_price(
    client, product: dict, branch_cur: Dict[str, Dict[str, Any]]
) -> Optional[float]:
    """price(P) / median(similar products' price), all in USD. None if unjudgeable."""
    cat = product.get("categoryId")
    if cat is None:
        return None  # no category → no well-defined niche

    own_branch = str(product.get("branchId"))
    own_usd = _to_usd(
        product.get("price"),
        product.get("currency"),
        (branch_cur.get(own_branch) or {}).get("exchangeRate"),
    )
    if own_usd is None:
        return None

    try:
        resp = await client.query_points(
            collection_name="products",
            query=RecommendQuery(
                recommend=RecommendInput(
                    positive=[_product_uuid(str(product["_id"]))],
                    strategy=RecommendStrategy.BEST_SCORE,
                )
            ),
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="categoryId", match=models.MatchValue(value=str(cat))
                    ),
                    models.FieldCondition(
                        key="availability", match=models.MatchValue(value=True)
                    ),
                ],
                must_not=[
                    models.FieldCondition(
                        key="branchId", match=models.MatchValue(value=own_branch)
                    ),
                ],
            ),
            limit=NEIGHBOR_K,
        )
    except Exception as e:
        logger.debug(f"recommend failed for product {product.get('_id')}: {e}")
        return None

    points = resp.points if hasattr(resp, "points") else resp
    neighbor_prices: List[float] = []
    for pt in points:
        payload = pt.payload or {}
        nb_branch = str(payload.get("branchId"))
        usd = _to_usd(
            payload.get("price"),
            payload.get("currency"),
            (branch_cur.get(nb_branch) or {}).get("exchangeRate"),
        )
        if usd is not None:
            neighbor_prices.append(usd)

    if len(neighbor_prices) < MIN_NEIGHBORS:
        return None
    market = statistics.median(neighbor_prices)
    if market <= 0:
        return None
    return own_usd / market


async def compute_price_positioning() -> Dict[str, int]:
    """Classify every store as economica/promedio/cara within its niche."""
    try:
        client = get_qdrant_client()
    except RuntimeError:
        logger.warning("Qdrant unavailable — skipping price positioning")
        return {"branches": 0, "classified": 0, "skipped": 0}

    db = get_database()
    branch_cur = await _branch_currency_map(db)

    products = await db["products"].find(
        {}, {"_id": 1, "branchId": 1, "categoryId": 1, "price": 1, "currency": 1}
    ).to_list(length=None)

    by_branch: Dict[str, List[dict]] = {}
    for p in products:
        by_branch.setdefault(str(p.get("branchId")), []).append(p)

    classified = 0
    skipped = 0
    now = datetime.utcnow()

    for branch_id, prods in by_branch.items():
        rels: List[float] = []
        for p in prods:
            r = await _relative_price(client, p, branch_cur)
            if r is not None:
                rels.append(r)

        if len(rels) < MIN_PRODUCTS_PER_BRANCH:
            # Not enough signal — clear any previous verdict so it can't go stale.
            await db["branches"].update_one(
                {"_id": _oid(branch_id)},
                {"$set": {
                    "priceTier": None,
                    "priceIndex": None,
                    "priceConfidence": len(rels),
                    "pricePositioningUpdatedAt": now,
                }},
            )
            skipped += 1
            continue

        index = statistics.median(rels)
        await db["branches"].update_one(
            {"_id": _oid(branch_id)},
            {"$set": {
                "priceTier": _classify(index),
                "priceIndex": round(index, 4),
                "priceConfidence": len(rels),
                "pricePositioningUpdatedAt": now,
            }},
        )
        classified += 1

    invalidate_branch_cache()
    logger.info(
        "Price positioning: branches=%s classified=%s skipped=%s",
        len(by_branch),
        classified,
        skipped,
    )
    return {"branches": len(by_branch), "classified": classified, "skipped": skipped}
