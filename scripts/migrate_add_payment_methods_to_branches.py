#!/usr/bin/env python3
"""
Migration script to add paymentMethodIds field to existing branches.
This script adds an empty paymentMethodIds array to all branches that don't have it.
"""
import asyncio
from clients import get_database


async def migrate_branches():
    """Add paymentMethodIds field to all branches."""
    db = get_database()
    branches_collection = db["branches"]
    
    # Find all branches without paymentMethodIds field
    branches_without_field = await branches_collection.count_documents({
        "paymentMethodIds": {"$exists": False}
    })
    
    print(f"Found {branches_without_field} branches without paymentMethodIds field")
    
    if branches_without_field == 0:
        print("All branches already have paymentMethodIds field. No migration needed.")
        return
    
    # Update all branches to add empty paymentMethodIds array
    result = await branches_collection.update_many(
        {"paymentMethodIds": {"$exists": False}},
        {"$set": {"paymentMethodIds": []}}
    )
    
    print(f"Updated {result.modified_count} branches with empty paymentMethodIds array")
    print("Migration completed successfully!")


if __name__ == "__main__":
    print("Starting migration: Add paymentMethodIds to branches")
    print("=" * 60)
    asyncio.run(migrate_branches())
