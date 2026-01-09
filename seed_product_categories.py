"""Seed script to insert product categories into MongoDB."""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient


async def seed_product_categories():
    """Insert product categories from JSON file into MongoDB."""
    # Load categories from JSON file
    json_path = Path(__file__).parent / "data" / "product_categories.json"

    with open(json_path, "r", encoding="utf-8") as f:
        categories_data = json.load(f)

    # Connect directly to MongoDB
    mongodb_url = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627"
    client = AsyncIOMotorClient(mongodb_url)
    db = client["llego"]
    collection = db["product_categories"]

    # Clear existing categories
    delete_result = await collection.delete_many({})
    print(f"Deleted {delete_result.deleted_count} existing product categories")

    # Insert new categories
    for category in categories_data:
        category["createdAt"] = datetime.utcnow()

    insert_result = await collection.insert_many(categories_data)
    print(f"Inserted {len(insert_result.inserted_ids)} product categories")

    # Display summary by branch type
    for branch_type in ["restaurante", "dulceria", "tienda"]:
        count = await collection.count_documents({"branchType": branch_type})
        print(f"  - {branch_type}: {count} categories")

    print("\n✓ Product categories seeded successfully")

    # Close connection
    client.close()


if __name__ == "__main__":
    asyncio.run(seed_product_categories())
