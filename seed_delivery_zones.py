"""
Seed script to populate H3 delivery zones covering La Habana.

Generates hexagonal zones at H3 resolution 7 (~4.78 km² per hex)
covering the metropolitan area of Havana and inserts them into
the delivery_zones MongoDB collection.

Usage:
    python seed_delivery_zones.py

Zones are created with default pricing in CUP that can be adjusted
later per-zone from an admin panel or directly in MongoDB.
"""

import asyncio
from datetime import datetime

import h3
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings

# ---------------------------------------------------------------------------
# Havana zone definitions
# ---------------------------------------------------------------------------
# Each entry defines a named area with a bounding polygon (lat, lng vertices)
# and optional pricing overrides.  Zones not matching any named area get
# generic "La Habana" defaults.
#
# Coordinates are approximate and meant to roughly delimit well-known
# municipalities / neighbourhoods.
#
# Pricing model:
#   deliveryFee = baseFee + max(0, distance_km - freeKm) * perKmFee
#   deliveryFee *= (1 + surchargePercent / 100)   if surcharge > 0
#   deliveryFee = min(deliveryFee, maxDeliveryFee) if cap set
#
# The distance is always measured from the BRANCH to the CUSTOMER.

HAVANA_AREAS = [
    {
        "name": "Habana Vieja",
        "polygon": [
            (23.130, -82.365),
            (23.130, -82.345),
            (23.145, -82.345),
            (23.145, -82.365),
        ],
        "baseFee": 250.0,
        "perKmFee": 80.0,
        "surchargePercent": 10.0,  # Alta demanda turística
    },
    {
        "name": "Centro Habana",
        "polygon": [
            (23.130, -82.385),
            (23.130, -82.365),
            (23.145, -82.365),
            (23.145, -82.385),
        ],
        "baseFee": 250.0,
        "perKmFee": 80.0,
        "surchargePercent": 5.0,
    },
    {
        "name": "Vedado",
        "polygon": [
            (23.120, -82.420),
            (23.120, -82.385),
            (23.145, -82.385),
            (23.145, -82.420),
        ],
        "baseFee": 300.0,
        "perKmFee": 100.0,
        "surchargePercent": 5.0,
    },
    {
        "name": "Miramar / Playa",
        "polygon": [
            (23.085, -82.475),
            (23.085, -82.390),
            (23.155, -82.390),
            (23.155, -82.475),
        ],
        "baseFee": 300.0,
        "perKmFee": 100.0,
        "surchargePercent": 0.0,
    },
    {
        "name": "Cerro / Diez de Octubre",
        "polygon": [
            (23.080, -82.400),
            (23.080, -82.360),
            (23.130, -82.360),
            (23.130, -82.400),
        ],
        "baseFee": 300.0,
        "perKmFee": 100.0,
        "surchargePercent": 0.0,
    },
    {
        "name": "Marianao / La Lisa",
        "polygon": [
            (23.040, -82.480),
            (23.040, -82.420),
            (23.100, -82.420),
            (23.100, -82.480),
        ],
        "baseFee": 350.0,
        "perKmFee": 120.0,
        "surchargePercent": 0.0,
    },
    {
        "name": "Guanabacoa / Regla",
        "polygon": [
            (23.100, -82.330),
            (23.100, -82.290),
            (23.140, -82.290),
            (23.140, -82.330),
        ],
        "baseFee": 400.0,
        "perKmFee": 120.0,
        "surchargePercent": 0.0,
    },
    {
        "name": "Boyeros / Santiago de las Vegas",
        "polygon": [
            (22.960, -82.420),
            (22.960, -82.360),
            (23.040, -82.360),
            (23.040, -82.420),
        ],
        "baseFee": 450.0,
        "perKmFee": 130.0,
        "surchargePercent": 0.0,
    },
    {
        "name": "Cotorro / San Miguel del Padrón",
        "polygon": [
            (23.020, -82.340),
            (23.020, -82.290),
            (23.080, -82.290),
            (23.080, -82.340),
        ],
        "baseFee": 450.0,
        "perKmFee": 130.0,
        "surchargePercent": 0.0,
    },
]

# Full Havana bounding box (captures anything the named areas miss)
HAVANA_BBOX = {
    "lat_min": 22.95,
    "lat_max": 23.20,
    "lng_min": -82.55,
    "lng_max": -82.28,
}

# Default pricing (CUP) for hexagons not inside any named area
DEFAULT_PRICING = {
    "baseFee": 350.0,
    "perKmFee": 100.0,
    "surchargePercent": 0.0,
}

H3_RESOLUTION = 7
CURRENCY = "CUP"
MAX_DELIVERY_FEE = 1500.0  # Cap global en CUP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_in_polygon(
    lat: float, lng: float, polygon: list[tuple[float, float]]
) -> bool:
    """Simple ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def _get_area_for_hex(lat: float, lng: float) -> dict | None:
    """Return the named area dict whose polygon contains (lat, lng), or None."""
    for area in HAVANA_AREAS:
        if _point_in_polygon(lat, lng, area["polygon"]):
            return area
    return None


def generate_havana_zones() -> list[dict]:
    """Generate delivery zone documents for all H3 hexagons covering Havana."""
    bbox_polygon = h3.LatLngPoly(
        [
            (HAVANA_BBOX["lat_min"], HAVANA_BBOX["lng_min"]),
            (HAVANA_BBOX["lat_min"], HAVANA_BBOX["lng_max"]),
            (HAVANA_BBOX["lat_max"], HAVANA_BBOX["lng_max"]),
            (HAVANA_BBOX["lat_max"], HAVANA_BBOX["lng_min"]),
        ]
    )

    hexagons = h3.polygon_to_cells(bbox_polygon, H3_RESOLUTION)
    now = datetime.utcnow()
    zones = []

    for hex_id in sorted(hexagons):
        lat, lng = h3.cell_to_latlng(hex_id)
        area = _get_area_for_hex(lat, lng)

        if area:
            name = area["name"]
            base_fee = area["baseFee"]
            per_km_fee = area["perKmFee"]
            surcharge = area["surchargePercent"]
        else:
            name = "La Habana"
            base_fee = DEFAULT_PRICING["baseFee"]
            per_km_fee = DEFAULT_PRICING["perKmFee"]
            surcharge = DEFAULT_PRICING["surchargePercent"]

        zone = {
            "_id": ObjectId(),
            "h3Index": hex_id,
            "resolution": H3_RESOLUTION,
            "name": name,
            "baseFee": base_fee,
            "perKmFee": per_km_fee,
            "currency": CURRENCY,
            "surchargePercent": surcharge,
            "isActive": True,
            "minOrderAmount": None,
            "maxDeliveryFee": MAX_DELIVERY_FEE,
            "city": "La Habana",
            "province": "La Habana",
            "createdAt": now,
            "updatedAt": now,
        }
        zones.append(zone)

    return zones


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


async def seed_delivery_zones():
    """Connect to MongoDB and insert delivery zones for La Habana."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    collection = db["delivery_zones"]

    existing_count = await collection.count_documents({"city": "La Habana"})
    if existing_count > 0:
        print(
            f"⚠️  Ya existen {existing_count} zonas para La Habana en la base de datos."
        )
        answer = input("¿Deseas eliminarlas y recrearlas? (s/N): ").strip().lower()
        if answer != "s":
            print("⏭️  Seed cancelado.")
            client.close()
            return
        deleted = await collection.delete_many({"city": "La Habana"})
        print(f"🗑️  Eliminadas {deleted.deleted_count} zonas existentes.")

    print("🌱 Generando zonas H3 para La Habana...")
    zones = generate_havana_zones()

    print(f"📦 Insertando {len(zones)} zonas en delivery_zones...")
    result = await collection.insert_many(zones)
    print(f"✅ Insertadas {len(result.inserted_ids)} zonas.")

    # Create indexes
    await collection.create_index("h3Index", unique=True, name="idx_h3_index_unique")
    await collection.create_index(
        [("city", 1), ("isActive", 1)], name="idx_city_active"
    )
    await collection.create_index(
        [("province", 1), ("isActive", 1)], name="idx_province_active"
    )
    await collection.create_index("isActive", name="idx_is_active")
    print("✅ Índices creados/verificados.")

    # Print summary by area name
    print(f"\n📊 Resumen por zona (moneda: {CURRENCY}):")
    print(
        f"   {'Zona':<35} {'Hexágonos':>10}  {'Base':>8}  {'$/km':>8}  {'Recargo':>8}"
    )
    print(f"   {'─' * 35} {'─' * 10}  {'─' * 8}  {'─' * 8}  {'─' * 8}")

    area_counts: dict[str, dict] = {}
    for z in zones:
        name = z["name"]
        if name not in area_counts:
            area_counts[name] = {
                "count": 0,
                "baseFee": z["baseFee"],
                "perKmFee": z["perKmFee"],
                "surcharge": z["surchargePercent"],
            }
        area_counts[name]["count"] += 1

    for name, info in sorted(area_counts.items(), key=lambda x: -x[1]["count"]):
        surcharge_str = f"{info['surcharge']:.0f}%" if info["surcharge"] > 0 else "—"
        print(
            f"   {name:<35} {info['count']:>10}  "
            f"{info['baseFee']:>7.0f}  "
            f"{info['perKmFee']:>7.0f}  "
            f"{surcharge_str:>8}"
        )

    print(f"\n   {'TOTAL':<35} {len(zones):>10}")
    print(f"\n✨ Delivery zones para La Habana configuradas exitosamente!")
    print(f"   Moneda: {CURRENCY}")
    print(f"   Max delivery fee cap: {MAX_DELIVERY_FEE:.0f} {CURRENCY}")
    print(
        f"   Resolución H3: {H3_RESOLUTION} (~{h3.cell_area(zones[0]['h3Index'], unit='km^2'):.2f} km² por hexágono)"
    )
    print(f"   El precio se calcula desde el NEGOCIO hasta el CLIENTE.")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed_delivery_zones())
