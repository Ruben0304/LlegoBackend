"""Seed script to insert product categories into MongoDB."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


async def seed_product_categories_from_db(db):
    """
    Insert product categories from JSON file into MongoDB.

    Args:
        db: MongoDB database instance

    Returns:
        bool: True if seeding was performed, False if skipped
    """
    collection = db["product_categories"]

    # Check if categories already exist
    existing_count = await collection.count_documents({})
    if existing_count > 0:
        print(
            f"ℹ Product categories already exist ({existing_count} found). Skipping seed."
        )
        return False

    # Load categories from JSON file
    json_path = ROOT_DIR / "data" / "product_categories.json"

    with open(json_path, "r", encoding="utf-8") as f:
        categories_data = json.load(f)

    # Insert new categories
    for category in categories_data:
        category["createdAt"] = datetime.utcnow()

    insert_result = await collection.insert_many(categories_data)
    print(f"✓ Inserted {len(insert_result.inserted_ids)} product categories")

    # Display summary by branch type
    for branch_type in ["restaurante", "dulceria", "tienda", "perfumeria"]:
        count = await collection.count_documents({"branchType": branch_type})
        print(f"  - {branch_type}: {count} categories")

    return True


async def seed_product_categories():
    """
    Standalone function to seed product categories (for manual execution).
    Connects to MongoDB directly.
    """
    # Connect directly to MongoDB
    mongodb_url = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627"
    client = AsyncIOMotorClient(mongodb_url)
    db = client["llego"]

    try:
        # Force reseed by clearing existing data
        collection = db["product_categories"]
        delete_result = await collection.delete_many({})
        print(f"Deleted {delete_result.deleted_count} existing product categories")

        # Load and insert categories
        json_path = ROOT_DIR / "data" / "product_categories.json"
        with open(json_path, "r", encoding="utf-8") as f:
            categories_data = json.load(f)

        for category in categories_data:
            category["createdAt"] = datetime.utcnow()

        insert_result = await collection.insert_many(categories_data)
        print(f"✓ Inserted {len(insert_result.inserted_ids)} product categories")

        # Display summary
        for branch_type in ["restaurante", "dulceria", "tienda", "perfumeria"]:
            count = await collection.count_documents({"branchType": branch_type})
            print(f"  - {branch_type}: {count} categories")

        print("\n✓ Product categories seeded successfully")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(seed_product_categories())
