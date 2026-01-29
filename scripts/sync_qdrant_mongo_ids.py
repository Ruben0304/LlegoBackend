"""
Script to synchronize Qdrant point IDs with MongoDB IDs.

This script fixes the mismatch between Qdrant point payloads (mongo_id field)
and actual MongoDB document IDs by matching on name fields.

Usage:
    python scripts/sync_qdrant_mongo_ids.py
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from qdrant_client.models import PointStruct

from clients.mongodb_client import get_database, connect_to_mongo, close_mongo_connection
from clients.qdrant_client import get_qdrant_client, connect_to_qdrant, close_qdrant_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Collection configurations
COLLECTIONS = {
    "products": {
        "qdrant_name": "products",
        "mongo_name": "products",
        "match_field": "name",  # Field to match on
        "embedding_fields": ["name", "description"],
    },
    "branches": {
        "qdrant_name": "branches",
        "mongo_name": "branches",
        "match_field": "name",
        "embedding_fields": ["name", "tipos"],
    },
    "businesses": {
        "qdrant_name": "businesses",
        "mongo_name": "bussisnes",  # Note: intentional typo in MongoDB
        "match_field": "name",
        "embedding_fields": ["name", "description"],
    },
}


async def get_all_qdrant_points(qdrant_client, collection_name: str) -> List[Any]:
    """Fetch all points from a Qdrant collection."""
    points = []
    offset = None

    logger.info(f"  Fetching all points from Qdrant collection: {collection_name}")

    while True:
        try:
            result = await qdrant_client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            batch_points, offset = result

            if not batch_points:
                break

            points.extend(batch_points)

            if offset is None:
                break

        except Exception as e:
            logger.error(f"  Error fetching points: {e}")
            break

    logger.info(f"  Fetched {len(points)} points from Qdrant")
    return points


async def find_mongo_document_by_name(db, collection_name: str, name: str) -> Optional[Dict[str, Any]]:
    """Find a MongoDB document by name field."""
    try:
        collection = db[collection_name]
        # Case-insensitive search
        document = await collection.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        return document
    except Exception as e:
        logger.error(f"  Error finding document by name '{name}': {e}")
        return None


async def sync_collection(
    db,
    qdrant_client,
    config: Dict[str, Any]
) -> Dict[str, int]:
    """
    Synchronize Qdrant mongo_id fields with MongoDB for a collection.

    Returns dict with stats: {matched, updated, not_found, errors}
    """
    qdrant_name = config["qdrant_name"]
    mongo_name = config["mongo_name"]
    match_field = config["match_field"]

    logger.info(f"\n{'='*80}")
    logger.info(f"🔄 Syncing collection: {qdrant_name} <-> {mongo_name}")
    logger.info(f"{'='*80}")

    stats = {
        "matched": 0,
        "updated": 0,
        "not_found": 0,
        "errors": 0
    }

    # Get all points from Qdrant
    points = await get_all_qdrant_points(qdrant_client, qdrant_name)

    if not points:
        logger.warning(f"  No points found in Qdrant collection: {qdrant_name}")
        return stats

    # Process each point
    updated_points = []

    for point in points:
        try:
            # Extract name from payload (handle both flat and metadata wrapper structures)
            payload = point.payload
            if "metadata" in payload:
                # Old structure with metadata wrapper
                name = payload.get("metadata", {}).get(match_field)
                old_mongo_id = payload.get("metadata", {}).get("mongo_id")
            else:
                # Flat structure
                name = payload.get(match_field)
                old_mongo_id = payload.get("mongo_id")

            if not name:
                logger.warning(f"  ⚠️  Point {point.id}: No '{match_field}' field found, skipping")
                stats["errors"] += 1
                continue

            # Find corresponding MongoDB document
            mongo_doc = await find_mongo_document_by_name(db, mongo_name, name)

            if not mongo_doc:
                logger.warning(f"  ❌ Point {point.id}: No MongoDB document found for '{match_field}={name}'")
                stats["not_found"] += 1
                continue

            correct_mongo_id = str(mongo_doc["_id"])

            # Check if mongo_id needs update
            if old_mongo_id == correct_mongo_id:
                logger.debug(f"  ✓ Point {point.id}: Already correct (name='{name}')")
                stats["matched"] += 1
                continue

            # Update payload with correct mongo_id (flat structure)
            new_payload = {
                "mongo_id": correct_mongo_id,
                match_field: name,
            }

            # Add other relevant fields from payload
            for key, value in payload.items():
                if key not in ["mongo_id", match_field, "metadata"]:
                    new_payload[key] = value
                # Also extract from metadata if it exists
                elif key == "metadata" and isinstance(value, dict):
                    for meta_key, meta_value in value.items():
                        if meta_key not in ["mongo_id", match_field]:
                            new_payload[meta_key] = meta_value

            # Create updated point
            updated_point = PointStruct(
                id=point.id,
                vector=point.vector,
                payload=new_payload,
            )

            updated_points.append(updated_point)

            logger.info(
                f"  🔄 Point {point.id}: '{name}' | "
                f"Old ID: {old_mongo_id[:12]}... → New ID: {correct_mongo_id[:12]}..."
            )
            stats["updated"] += 1

        except Exception as e:
            logger.error(f"  ❌ Error processing point {point.id}: {e}")
            stats["errors"] += 1

    # Batch update Qdrant
    if updated_points:
        logger.info(f"\n  📝 Updating {len(updated_points)} points in Qdrant...")

        batch_size = 100
        for i in range(0, len(updated_points), batch_size):
            batch = updated_points[i:i + batch_size]
            try:
                await qdrant_client.upsert(
                    collection_name=qdrant_name,
                    points=batch,
                )
                logger.info(f"    Batch {i//batch_size + 1}: Updated {len(batch)} points")
            except Exception as e:
                logger.error(f"    Error updating batch: {e}")
                stats["errors"] += len(batch)

    # Print summary
    logger.info(f"\n  📊 Summary for {qdrant_name}:")
    logger.info(f"    ✅ Already matched: {stats['matched']}")
    logger.info(f"    🔄 Updated: {stats['updated']}")
    logger.info(f"    ❌ Not found in MongoDB: {stats['not_found']}")
    logger.info(f"    ⚠️  Errors: {stats['errors']}")

    return stats


async def sync_all_collections_from_db(db=None):
    """
    Synchronize all collections using existing database connections.

    Args:
        db: Optional existing MongoDB database connection. If None, will connect.
    """
    logger.info("\n" + "="*80)
    logger.info("🚀 Starting Qdrant-MongoDB ID Synchronization")
    logger.info("="*80)

    # Use provided connection or connect
    should_close = False
    if db is None:
        logger.info("\n📡 Connecting to databases...")
        await connect_to_mongo()
        await connect_to_qdrant()
        db = get_database()
        should_close = True

    try:
        qdrant_client = get_qdrant_client()

        total_stats = {
            "matched": 0,
            "updated": 0,
            "not_found": 0,
            "errors": 0
        }

        # Sync each collection
        for collection_type, config in COLLECTIONS.items():
            stats = await sync_collection(db, qdrant_client, config)

            # Accumulate stats
            for key in total_stats:
                total_stats[key] += stats[key]

        # Final summary
        logger.info(f"\n{'='*80}")
        logger.info("📊 FINAL SUMMARY - All Collections")
        logger.info(f"{'='*80}")
        logger.info(f"  ✅ Already matched: {total_stats['matched']}")
        logger.info(f"  🔄 Updated: {total_stats['updated']}")
        logger.info(f"  ❌ Not found in MongoDB: {total_stats['not_found']}")
        logger.info(f"  ⚠️  Errors: {total_stats['errors']}")
        logger.info(f"{'='*80}")

        if total_stats['updated'] > 0:
            logger.info("\n✅ Synchronization complete! Qdrant IDs now match MongoDB.")
        else:
            logger.info("\n✅ All IDs were already in sync. No updates needed.")

    except Exception as e:
        logger.error(f"\n❌ Error during synchronization: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if should_close:
            await close_mongo_connection()
            await close_qdrant_connection()


async def sync_all_collections():
    """Synchronize all collections (standalone version)."""
    await sync_all_collections_from_db(db=None)


if __name__ == "__main__":
    asyncio.run(sync_all_collections())
