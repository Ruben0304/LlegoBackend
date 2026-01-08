"""Utility functions for orders module."""
from datetime import datetime
from typing import Tuple
import math

from clients.mongodb_client import get_database


async def generate_order_number() -> str:
    """Generate unique human-readable order number: ORD-YYYY-XXXXXX."""
    db = get_database()
    year = datetime.now().year
    
    # Use MongoDB findAndModify to get atomic sequence
    result = await db.counters.find_one_and_update(
        {"_id": f"order_sequence_{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    
    sequence = result["seq"]
    return f"ORD-{year}-{sequence:06d}"


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
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
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def calculate_delivery_fee(
    branch_coords: Tuple[float, float],
    delivery_coords: Tuple[float, float],
    base_fee: float = 1.50,
    per_km_fee: float = 0.50,
    free_km: float = 2.0
) -> float:
    """
    Calculate delivery fee based on distance.
    
    Args:
        branch_coords: (longitude, latitude) of branch
        delivery_coords: (longitude, latitude) of delivery address
        base_fee: Base delivery fee in USD
        per_km_fee: Fee per km after free_km
        free_km: Distance included in base fee
    
    Returns:
        Delivery fee in USD
    """
    distance_km = haversine_distance(branch_coords, delivery_coords)
    
    if distance_km <= free_km:
        return base_fee
    
    return round(base_fee + (distance_km - free_km) * per_km_fee, 2)


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
