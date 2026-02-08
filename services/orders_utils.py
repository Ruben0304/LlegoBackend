"""Utility functions for orders module."""

import math
from datetime import datetime
from typing import Optional, Tuple

import h3

from clients.mongodb_client import get_database

# Default H3 resolution for delivery zones
H3_RESOLUTION = 7


async def generate_order_number() -> str:
    """Generate unique human-readable order number: ORD-YYYY-XXXXXX."""
    db = get_database()
    year = datetime.now().year

    # Use MongoDB findAndModify to get atomic sequence
    result = await db.counters.find_one_and_update(
        {"_id": f"order_sequence_{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )

    sequence = result["seq"]
    return f"ORD-{year}-{sequence:06d}"


def haversine_distance(
    coord1: Tuple[float, float], coord2: Tuple[float, float]
) -> float:
    """
    Calculate the great circle distance between two points on earth (in km).

    Args:
        coord1: (longitude, latitude) of first point
        coord2: (longitude, latitude) of second point

    Returns:
        Distance in kilometers
    """
    lon1, lat1 = coord1
    lon2, lat2 = coord2

    R = 6371  # Earth's radius in kilometers

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def coords_to_h3(lat: float, lng: float, resolution: int = H3_RESOLUTION) -> str:
    """
    Convert latitude/longitude to an H3 hexagonal index.

    Args:
        lat: Latitude
        lng: Longitude
        resolution: H3 resolution level (default 7, ~5.16 km² per hex)

    Returns:
        H3 index string, e.g. "872a1008fffffff"
    """
    return h3.latlng_to_cell(lat, lng, resolution)


def calculate_delivery_fee(
    branch_coords: Tuple[float, float],
    delivery_coords: Tuple[float, float],
    base_fee: float = 300.0,
    per_km_fee: float = 100.0,
    free_km: float = 2.0,
) -> float:
    """
    Calculate delivery fee based on distance (fallback / simple mode).

    Args:
        branch_coords: (longitude, latitude) of branch
        delivery_coords: (longitude, latitude) of delivery address
        base_fee: Base delivery fee in CUP
        per_km_fee: Fee per km after free_km in CUP
        free_km: Distance included in base fee

    Returns:
        Delivery fee in CUP
    """
    distance_km = haversine_distance(branch_coords, delivery_coords)

    if distance_km <= free_km:
        return base_fee

    return round(base_fee + (distance_km - free_km) * per_km_fee, 2)


async def calculate_delivery_fee_h3(
    branch_coords: Tuple[float, float],
    delivery_coords: Tuple[float, float],
    subtotal: float = 0.0,
) -> Tuple[float, Optional[str]]:
    """
    Calculate delivery fee using H3 hexagonal zone pricing (CUP).

    Looks up the destination's H3 zone in the delivery_zones collection.
    The fee is calculated based on the distance from the branch to the
    customer's delivery address, using the zone's configured rates.
    If no zone is found, falls back to the default distance-based calculation.

    Args:
        branch_coords: (longitude, latitude) of branch
        delivery_coords: (longitude, latitude) of delivery address
        subtotal: Order subtotal in CUP (used for minOrderAmount validation)

    Returns:
        Tuple of (delivery_fee_in_cup, h3_index_or_none)
        - h3_index is returned when a zone was matched, None when using fallback
    """
    dest_lng, dest_lat = delivery_coords
    dest_h3 = coords_to_h3(dest_lat, dest_lng)

    db = get_database()
    zone = await db.delivery_zones.find_one({"h3Index": dest_h3, "isActive": True})

    if not zone:
        # No zone configured for this hex — use default distance-based fee
        fee = calculate_delivery_fee(branch_coords, delivery_coords)
        return fee, None

    # Validate minimum order amount if configured
    min_order = zone.get("minOrderAmount")
    if min_order is not None and subtotal < min_order:
        raise ValueError(f"El monto mínimo para envío en esta zona es ${min_order:.2f}")

    # Calculate distance
    distance_km = haversine_distance(branch_coords, delivery_coords)

    # Base fee from the zone
    base = zone["baseFee"]
    per_km = zone.get("perKmFee", 100.0)
    surcharge_pct = zone.get("surchargePercent", 0.0)
    max_fee = zone.get("maxDeliveryFee")

    # Fee = base + extra km cost
    free_km = 2.0
    if distance_km <= free_km:
        fee = base
    else:
        fee = base + (distance_km - free_km) * per_km

    # Apply surcharge
    if surcharge_pct > 0:
        fee = fee * (1 + surcharge_pct / 100)

    fee = round(fee, 2)

    # Cap at max if configured
    if max_fee is not None:
        fee = min(fee, max_fee)

    return fee, dest_h3


def estimate_delivery_time(distance_km: float, avg_speed_kmh: float = 25.0) -> int:
    """
    Estimate delivery time in minutes.

    Args:
        distance_km: Distance in kilometers
        avg_speed_kmh: Average delivery speed in km/h

    Returns:
        Estimated time in minutes
    """
    # Base preparation time + travel time
    prep_time = 15  # minutes
    travel_time = (distance_km / avg_speed_kmh) * 60

    return int(prep_time + travel_time)
