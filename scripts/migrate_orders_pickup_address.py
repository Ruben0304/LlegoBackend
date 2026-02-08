"""
Migration script to populate pickupAddress field on all orders
based on the associated branch's address and coordinates.

Run with: python scripts/migrate_orders_pickup_address.py
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = (
    "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627"
)
DATABASE_NAME = "llego"


async def migrate_pickup_address():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    orders = db.orders
    branches = db.branches

    print("Starting pickupAddress migration...")

    # Only process orders without pickupAddress
    query = {"pickupAddress": {"$exists": False}}
    total = await orders.count_documents(query)
    print(f"Found {total} orders without pickupAddress")

    updated = 0
    skipped = 0

    async for order in orders.find(query):
        branch_id = order.get("branchId")
        if not branch_id:
            skipped += 1
            continue

        branch = await branches.find_one({"_id": branch_id})
        if not branch:
            print(f"  ⚠ Branch not found for order {order['_id']}, skipping")
            skipped += 1
            continue

        pickup_address = {
            "street": branch.get("address"),
            "coordinates": branch.get(
                "coordinates", {"type": "Point", "coordinates": [0, 0]}
            ),
        }

        await orders.update_one(
            {"_id": order["_id"]},
            {"$set": {"pickupAddress": pickup_address}},
        )
        updated += 1

    print(f"\n✅ Done: {updated} updated, {skipped} skipped")
    client.close()


if __name__ == "__main__":
    asyncio.run(migrate_pickup_address())
