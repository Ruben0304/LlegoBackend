"""Seed the vehicles catalog with the initial vehicle types (triciclo & bicicleta)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.mongodb_client import get_database  # noqa: E402 — path setup above
from domain.orders import VehicleType  # noqa: E402
from repositories.vehicle_repository import VehicleRepository  # noqa: E402


VEHICLES = [
    {"name": "Bicicleta", "slug": VehicleType.BICICLETA},
    {"name": "Triciclo",  "slug": VehicleType.TRICICLO},
]


async def seed():
    repo = VehicleRepository()
    print("Seeding vehicles catalog…")
    for v in VEHICLES:
        vehicle = await repo.upsert_seed(name=v["name"], slug=v["slug"])
        print(f"  ✓ {vehicle.name} (id={vehicle.id}  slug={vehicle.slug.value})")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
