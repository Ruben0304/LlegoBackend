"""Business repository for database operations.

Hybrid repository pattern:
- GET operations: MongoDB (source of truth for complete data)
- Search: Qdrant vector similarity (semantic search)
- Create/Update/Delete: Sync both databases
"""
from typing import List, Optional, Dict, Any
import uuid

from bson import ObjectId
from clients import get_database, get_qdrant_client
from domain.models import Business
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct
from services.embeddings.gemini_service import GeminiEmbeddingService
from utils.cache import (
    get_cached, set_cached, invalidate_business_cache,
    get_business_cache_key, TTL_DEFAULT, should_cache_result
)


class BusinessRepository:
    mongo_collection_name = "bussisnes"  # Note: intentional typo for compatibility
    qdrant_collection_name = "businesses"

    # RAG fields stored in Qdrant
    rag_fields = {"name", "description"}

    @staticmethod
    def _to_object_id(id_value: str):
        """Convert string ID to ObjectId for MongoDB queries."""
        try:
            return ObjectId(id_value)
        except Exception:
            # If it's not a valid ObjectId string, return as-is
            return id_value

    # --- GET Methods (MongoDB) ---

    async def get_all(self) -> List[Business]:
        """Get all businesses from MongoDB with caching."""
        cache_key = get_business_cache_key("all")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Business(**b) for b in cached]

        try:
            print("→ Fetching all businesses from MongoDB")
            db = get_database()
            cursor = db[self.mongo_collection_name].find()
            documents = await cursor.to_list(length=None)

            # Ensure IDs are strings
            for doc in documents:
                if isinstance(doc.get("_id"), ObjectId):
                    doc["_id"] = str(doc["_id"])
                if isinstance(doc.get("ownerId"), ObjectId):
                    doc["ownerId"] = str(doc["ownerId"])

            businesses = [Business(**doc) for doc in documents]

            # Cache the results only if not too large
            if should_cache_result(businesses):
                serialized = [b.model_dump() for b in businesses]
                set_cached(cache_key, serialized, TTL_DEFAULT)
                print(f"✓ Cached {len(businesses)} businesses (get_all)")
            else:
                print(f"⚠ Skipped caching {len(businesses)} businesses (exceeds limit)")

            return businesses

        except Exception as e:
            print(f"Error fetching all businesses from MongoDB: {e}")
            return []

    async def get_by_id(self, business_id: str) -> Optional[Business]:
        """Get business by ID from MongoDB with caching."""
        cache_key = get_business_cache_key(f"id:{business_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            return Business(**cached)

        try:
            print(f"→ Fetching business {business_id} from MongoDB")
            db = get_database()
            # Try both ObjectId and string to handle mixed data
            doc = await db[self.mongo_collection_name].find_one({
                "$or": [
                    {"_id": self._to_object_id(business_id)},
                    {"_id": business_id}
                ]
            })

            if doc:
                # Ensure _id is stored as string in the model
                if isinstance(doc.get("_id"), ObjectId):
                    doc["_id"] = str(doc["_id"])
                business = Business(**doc)
                # Cache the result
                set_cached(cache_key, business.model_dump(), TTL_DEFAULT)
                return business
            return None

        except Exception as e:
            print(f"Error fetching business {business_id} from MongoDB: {e}")
            return None

    async def get_by_ids(self, business_ids: List[str]) -> List[Business]:
        """Get multiple businesses by IDs from MongoDB with caching."""
        if not business_ids:
            return []

        cache_key = get_business_cache_key(f"ids:{','.join(sorted(business_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Business(**b) for b in cached]

        try:
            print(f"→ Fetching {len(business_ids)} businesses from MongoDB")
            db = get_database()
            # Convert to ObjectIds and also keep original strings
            object_ids = [self._to_object_id(bid) for bid in business_ids]
            cursor = db[self.mongo_collection_name].find({
                "$or": [
                    {"_id": {"$in": object_ids}},
                    {"_id": {"$in": business_ids}}
                ]
            })
            documents = await cursor.to_list(length=None)

            # Ensure _id is string in models
            for doc in documents:
                if isinstance(doc.get("_id"), ObjectId):
                    doc["_id"] = str(doc["_id"])

            businesses = [Business(**doc) for doc in documents]

            # Cache the results
            serialized = [b.model_dump() for b in businesses]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return businesses

        except Exception as e:
            print(f"Error fetching businesses by IDs from MongoDB: {e}")
            return []

    async def get_by_owner(self, owner_id: str) -> List[Business]:
        """Get businesses by owner ID from MongoDB."""
        try:
            db = get_database()
            # Try both ObjectId and string for ownerId
            cursor = db[self.mongo_collection_name].find({
                "$or": [
                    {"ownerId": self._to_object_id(owner_id)},
                    {"ownerId": owner_id}
                ]
            })
            documents = await cursor.to_list(length=None)

            # Ensure IDs are strings in models
            for doc in documents:
                if isinstance(doc.get("_id"), ObjectId):
                    doc["_id"] = str(doc["_id"])
                if isinstance(doc.get("ownerId"), ObjectId):
                    doc["ownerId"] = str(doc["ownerId"])

            return [Business(**doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching businesses by owner from MongoDB: {e}")
            return []

    # --- Search Method (Qdrant Vector Similarity) ---

    async def search(self, query: str, limit: int = 20) -> List[Business]:
        """Search businesses using Qdrant vector similarity."""
        try:
            # Generate embedding for query
            embedding_service = GeminiEmbeddingService()
            query_vector = embedding_service.generate_embedding(query)

            qdrant_client = get_qdrant_client()

            # Vector similarity search
            results = await qdrant_client.search(
                collection_name=self.qdrant_collection_name,
                query_vector=query_vector,
                limit=limit,
            )

            if not results:
                return []

            # Extract mongo_ids from results
            mongo_ids = []
            for result in results:
                mongo_id = result.payload.get("mongo_id")
                if mongo_id:
                    mongo_ids.append(mongo_id)

            # Fetch complete documents from MongoDB
            if mongo_ids:
                return await self.get_by_ids(mongo_ids)

            return []

        except Exception as e:
            print(f"Error searching businesses in Qdrant: {e}")
            return []

    # --- Create Method (MongoDB + Qdrant) ---

    async def create(self, business: Business) -> Business:
        """Create a new business in both MongoDB and Qdrant."""
        try:
            db = get_database()

            # 1. Insert into MongoDB (complete document)
            doc = business.model_dump(by_alias=True)
            await db[self.mongo_collection_name].insert_one(doc)

            # 2. Insert into Qdrant (RAG fields + embedding)
            await self._upsert_to_qdrant(business)

            # Invalidate cache for all businesses
            invalidate_business_cache()

            return business

        except Exception as e:
            print(f"Error creating business: {e}")
            raise e

    # --- Update Method (MongoDB + Qdrant if RAG fields changed) ---

    async def update(self, business_id: str, updates: Dict[str, Any]) -> Optional[Business]:
        """Update a business in MongoDB and Qdrant (if RAG fields changed)."""
        try:
            db = get_database()

            # Verify business exists
            current = await self.get_by_id(business_id)
            if not current:
                return None

            # 1. Update MongoDB (try both ObjectId and string)
            await db[self.mongo_collection_name].update_one(
                {
                    "$or": [
                        {"_id": self._to_object_id(business_id)},
                        {"_id": business_id}
                    ]
                },
                {"$set": updates}
            )

            # 2. If RAG fields changed, update Qdrant
            if self.rag_fields.intersection(updates.keys()):
                updated_business = await self.get_by_id(business_id)
                if updated_business:
                    await self._upsert_to_qdrant(updated_business)

            # Invalidate cache for this business and all businesses
            invalidate_business_cache(business_id=business_id)
            invalidate_business_cache()  # Invalidate get_all cache

            return await self.get_by_id(business_id)

        except Exception as e:
            print(f"Error updating business {business_id}: {e}")
            raise e

    async def update_field(self, business_id: str, field: str, value: Any) -> Optional[Business]:
        """Update a single field of a business."""
        return await self.update(business_id, {field: value})

    # --- Delete Method (MongoDB + Qdrant) ---

    async def delete(self, business_id: str) -> bool:
        """Delete a business from both MongoDB and Qdrant."""
        try:
            db = get_database()

            # 1. Delete from MongoDB (try both ObjectId and string)
            result = await db[self.mongo_collection_name].delete_one({
                "$or": [
                    {"_id": self._to_object_id(business_id)},
                    {"_id": business_id}
                ]
            })

            if result.deleted_count == 0:
                return False

            # 2. Delete from Qdrant
            await self._delete_from_qdrant(business_id)

            # Invalidate cache
            invalidate_business_cache(business_id=business_id)
            invalidate_business_cache()  # Invalidate get_all cache

            return True

        except Exception as e:
            print(f"Error deleting business {business_id}: {e}")
            return False

    # --- Qdrant Helper Methods ---

    async def _upsert_to_qdrant(self, business: Business):
        """Upsert business to Qdrant with RAG-only payload."""
        try:
            embedding_service = GeminiEmbeddingService()
            text_to_embed = f"{business.name} {business.description or ''}"
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()

            # First, try to find existing point
            existing = await self._find_qdrant_point(business.id)

            # RAG-only payload
            payload = {
                "mongo_id": business.id,
                "name": business.name,
                "description": business.description,
            }

            point_id = existing.id if existing else str(uuid.uuid4())
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            )

            await qdrant_client.upsert(
                collection_name=self.qdrant_collection_name,
                points=[point],
            )

        except Exception as e:
            print(f"Error upserting business to Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _delete_from_qdrant(self, business_id: str):
        """Delete business from Qdrant by mongo_id."""
        try:
            qdrant_client = get_qdrant_client()

            # Find point by mongo_id
            existing = await self._find_qdrant_point(business_id)
            if existing:
                await qdrant_client.delete(
                    collection_name=self.qdrant_collection_name,
                    points_selector=qdrant_models.PointIdsList(
                        points=[existing.id]
                    ),
                )

        except Exception as e:
            print(f"Error deleting business from Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _find_qdrant_point(self, mongo_id: str):
        """Find Qdrant point by mongo_id."""
        try:
            qdrant_client = get_qdrant_client()

            result = await qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="mongo_id",
                            match=qdrant_models.MatchValue(value=mongo_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )

            points, _ = result
            return points[0] if points else None

        except Exception as e:
            print(f"Error finding Qdrant point: {e}")
            return None
