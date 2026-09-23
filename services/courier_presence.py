"""Shared courier-presence snapshot logic.

Extracted from schema/orders/subscriptions.py so the same Redis-backed
snapshot can be consumed two ways: the existing `couriers_presence_stream`
WebSocket subscription (polls this every ~2s) and the one-shot
`admin_couriers_presence` GraphQL query (schema/orders/queries.py), which
Panel Admin polls over plain HTTP every ~5s for its couriers map — see the
"Pedidos en vivo" plan for why polling was chosen over subscriptions there.
"""

import json
from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from clients import get_database
from schema.orders.types import CoordinatesType, CourierPresenceType
from utils.rate_limit import redis_client

COURIER_ONLINE_KEY_PREFIX = "presence:courier:"


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Supports the isoformat() we stored (naive UTC)
        return datetime.fromisoformat(value)
    except Exception:
        return None


def fetch_courier_presence_snapshot_sync() -> List[CourierPresenceType]:
    """
    Sync Redis read: returns a snapshot of currently-online couriers.

    Uses scan_iter (safe-ish) and a pipeline for efficiency. Call via
    `asyncio.to_thread(...)` from async code.
    """
    if redis_client is None:
        return []

    loc_keys = list(
        redis_client.scan_iter(match=f"{COURIER_ONLINE_KEY_PREFIX}*:loc", count=200)
    )
    if not loc_keys:
        return []

    pipe = redis_client.pipeline()
    for k in loc_keys:
        pipe.get(k)
    loc_values = pipe.execute()

    results: List[CourierPresenceType] = []
    for key, raw in zip(loc_keys, loc_values):
        if not raw:
            continue
        # key: presence:courier:{id}:loc
        try:
            parts = str(key).split(":")
            delivery_person_id = parts[2]  # courier:{id}
            if delivery_person_id == "courier":
                # Unexpected shape; skip
                continue
        except Exception:
            continue

        try:
            payload = json.loads(raw)
        except Exception:
            continue

        coords = payload.get("coordinates") or []
        location = None
        if isinstance(coords, list) and len(coords) >= 2:
            try:
                location = CoordinatesType(
                    type=payload.get("type") or "Point",
                    coordinates=[float(coords[0]), float(coords[1])],
                )
            except Exception:
                location = None

        results.append(
            CourierPresenceType(
                deliveryPersonId=str(delivery_person_id),
                isOnline=True,
                location=location,
                timestamp=_parse_iso_dt(payload.get("timestamp")),
                orderId=payload.get("orderId"),
            )
        )
    return results


async def enrich_courier_snapshot(
    snapshot: List[CourierPresenceType],
) -> List[CourierPresenceType]:
    """
    Enrich a Redis-only courier snapshot with profile fields (name, phone,
    profileImageUrl, vehicleType) from the `delivery_persons` collection.

    Performs a single batch query for all couriers in the snapshot.
    """
    if not snapshot:
        return snapshot

    ids: List[ObjectId] = []
    for c in snapshot:
        try:
            ids.append(ObjectId(c.deliveryPersonId))
        except Exception:
            # Skip ids that aren't valid ObjectIds
            continue

    if not ids:
        return snapshot

    db = get_database()
    cursor = db["delivery_persons"].find(
        {"_id": {"$in": ids}},
        {
            "name": 1,
            "phone": 1,
            "profileImageUrl": 1,
            "vehicleType": 1,
            "rating": 1,
            "totalDeliveries": 1,
        },
    )
    profiles_by_id: dict = {}
    async for doc in cursor:
        profiles_by_id[str(doc["_id"])] = doc

    for c in snapshot:
        profile = profiles_by_id.get(c.deliveryPersonId)
        if not profile:
            continue
        c.name = profile.get("name")
        c.phone = profile.get("phone")
        c.profileImageUrl = profile.get("profileImageUrl")
        vt = profile.get("vehicleType")
        # vehicleType may be stored as a Pydantic Enum value or plain string
        c.vehicleType = vt.value if hasattr(vt, "value") else vt
        c.rating = profile.get("rating")
        c.totalDeliveries = profile.get("totalDeliveries")

    return snapshot


async def get_courier_presence_snapshot() -> List[CourierPresenceType]:
    """One-shot async helper: fetch + enrich in one call, for plain queries."""
    import asyncio

    snapshot = await asyncio.to_thread(fetch_courier_presence_snapshot_sync)
    return await enrich_courier_snapshot(snapshot)
