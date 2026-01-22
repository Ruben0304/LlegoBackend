"""
Migration script: Qdrant → MongoDB for branches, businesses, and products.

This script migrates complete data from Qdrant to MongoDB, and optionally
reduces Qdrant payloads to only RAG-relevant fields.

Runs automatically on server startup if MongoDB collections are empty.
"""
import logging
import asyncio
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from clients.mongodb_client import get_database, connect_to_mongo, close_mongo_connection
from clients.qdrant_client import get_qdrant_client, connect_to_qdrant, close_qdrant_connection
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService

logger = logging.getLogger(__name__)

# Collection mappings
COLLECTIONS = {
    "businesses": {
        "qdrant_name": "businesses",
        "mongo_name": "bussisnes",  # Note: intentional typo for compatibility
        "rag_fields": ["mongo_id", "name", "description"],
        "embedding_fields": ["name", "description"],
    },
    "branches": {
        "qdrant_name": "branches",
        "mongo_name": "branches",
        "rag_fields": ["mongo_id", "name", "tipos"],
        "embedding_fields": ["name", "tipos"],
    },
    "products": {
        "qdrant_name": "products",
        "mongo_name": "products",
        "rag_fields": ["mongo_id", "name", "price", "description"],
        "embedding_fields": ["name", "description"],
    },
}


async def _get_all_qdrant_points(qdrant_client, collection_name: str) -> List[Any]:
    """Scroll through all points in a Qdrant collection."""
    points = []
    offset = None

    while True:
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

    return points


def _point_to_mongo_document(point, entity_type: str) -> Optional[Dict[str, Any]]:
    """Convert Qdrant point payload to MongoDB document."""
    try:
        metadata = point.payload.get("metadata", {})

        # Use mongo_id as _id
        mongo_id = metadata.get("mongo_id")
        if not mongo_id:
            return None

        # Build document from metadata
        document = {"_id": mongo_id}

        # Copy all metadata fields except mongo_id
        for key, value in metadata.items():
            if key != "mongo_id":
                document[key] = value

        return document

    except Exception as e:
        logger.error(f"Error converting point to document: {e}")
        return None


def _extract_rag_payload(metadata: Dict[str, Any], rag_fields: List[str]) -> Dict[str, Any]:
    """Extract only RAG-relevant fields from metadata."""
    return {field: metadata.get(field) for field in rag_fields if field in metadata or field == "mongo_id"}


async def _migrate_collection(db, qdrant_client, config: Dict[str, Any]) -> int:
    """Migrate a single collection from Qdrant to MongoDB."""
    qdrant_name = config["qdrant_name"]
    mongo_name = config["mongo_name"]

    # Check if MongoDB collection already has data
    mongo_collection = db[mongo_name]
    existing_count = await mongo_collection.count_documents({})

    if existing_count > 0:
        logger.info(f"  ✓ {mongo_name}: Already has {existing_count} documents, skipping migration")
        return 0

    # Get all points from Qdrant
    logger.info(f"  → {qdrant_name}: Fetching from Qdrant...")
    try:
        points = await _get_all_qdrant_points(qdrant_client, qdrant_name)
    except Exception as e:
        logger.warning(f"  ⚠ {qdrant_name}: Could not fetch from Qdrant: {e}")
        return 0

    if not points:
        logger.info(f"  ⚠ {qdrant_name}: No points found in Qdrant")
        return 0

    # Convert to MongoDB documents
    documents = []
    for point in points:
        doc = _point_to_mongo_document(point, config["qdrant_name"])
        if doc:
            documents.append(doc)

    if not documents:
        logger.info(f"  ⚠ {qdrant_name}: No valid documents to migrate")
        return 0

    # Insert into MongoDB
    try:
        result = await mongo_collection.insert_many(documents)
        migrated_count = len(result.inserted_ids)
        logger.info(f"  ✓ {mongo_name}: Migrated {migrated_count} documents to MongoDB")
        return migrated_count
    except Exception as e:
        logger.error(f"  ✗ {mongo_name}: Error inserting documents: {e}")
        return 0


async def _update_qdrant_rag_payloads(qdrant_client, config: Dict[str, Any]) -> int:
    """Update Qdrant points to keep only RAG-relevant fields (flat structure)."""
    qdrant_name = config["qdrant_name"]
    rag_fields = config["rag_fields"]

    logger.info(f"  → {qdrant_name}: Checking Qdrant payload structure...")

    try:
        points = await _get_all_qdrant_points(qdrant_client, qdrant_name)
    except Exception as e:
        logger.warning(f"  ⚠ {qdrant_name}: Could not fetch points for RAG update: {e}")
        return 0

    if not points:
        return 0

    # Check if first point already has flat structure (no metadata wrapper)
    first_payload = points[0].payload if points else {}
    if "mongo_id" in first_payload and "metadata" not in first_payload:
        logger.info(f"  ✓ {qdrant_name}: Already has flat RAG structure, skipping update")
        return 0

    # Create new points with reduced payload (flat structure)
    updated_points = []
    for point in points:
        # Handle both old (with metadata wrapper) and new (flat) structures
        if "metadata" in point.payload:
            metadata = point.payload.get("metadata", {})
        else:
            metadata = point.payload

        rag_payload = _extract_rag_payload(metadata, rag_fields)

        # Skip if no mongo_id found
        if not rag_payload.get("mongo_id"):
            continue

        updated_point = PointStruct(
            id=point.id,
            vector=point.vector,
            payload=rag_payload,  # Flat structure, no metadata wrapper
        )
        updated_points.append(updated_point)

    if not updated_points:
        logger.info(f"  ⚠ {qdrant_name}: No valid points to update")
        return 0

    # Upsert in batches
    batch_size = 100
    updated_count = 0
    for i in range(0, len(updated_points), batch_size):
        batch = updated_points[i:i + batch_size]
        await qdrant_client.upsert(
            collection_name=qdrant_name,
            points=batch,
        )
        updated_count += len(batch)

    logger.info(f"  ✓ {qdrant_name}: Updated {updated_count} points with RAG-only payload (flat structure)")
    return updated_count


async def migrate_qdrant_to_mongo_from_db(db, update_qdrant_payloads: bool = True):
    """
    Migrate data from Qdrant to MongoDB.

    Args:
        db: MongoDB database instance
        update_qdrant_payloads: If True, also update Qdrant payloads to keep only RAG fields
                                (defaults to True to ensure Qdrant has the correct structure)
    """
    logger.info("🔄 Starting Qdrant → MongoDB migration check...")

    try:
        qdrant_client = get_qdrant_client()
    except RuntimeError:
        logger.warning("⚠ Qdrant client not available, skipping migration")
        return

    total_migrated = 0

    for entity_type, config in COLLECTIONS.items():
        migrated = await _migrate_collection(db, qdrant_client, config)
        total_migrated += migrated

        # Update Qdrant payloads to RAG-only structure (important for search compatibility)
        if update_qdrant_payloads:
            await _update_qdrant_rag_payloads(qdrant_client, config)

    if total_migrated > 0:
        logger.info(f"✅ Migration complete! Migrated {total_migrated} total documents to MongoDB")
    else:
        logger.info("✅ Migration check complete, no migration needed")


async def migrate_qdrant_to_mongo():
    """Standalone migration function (for CLI usage)."""
    print("🔄 Starting Qdrant → MongoDB migration...")

    # Connect to both databases
    await connect_to_mongo()
    await connect_to_qdrant()

    try:
        db = get_database()
        await migrate_qdrant_to_mongo_from_db(db, update_qdrant_payloads=False)
    finally:
        await close_mongo_connection()
        await close_qdrant_connection()

    print("✅ Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate_qdrant_to_mongo())
