"""Branch repository for database operations.

Hybrid repository pattern:
- GET operations: MongoDB (source of truth for complete data)
- Search: Qdrant vector similarity (semantic search)
- Create/Update/Delete: Sync both databases
"""

import re
from typing import Any, Dict, List, Optional

from bson import ObjectId
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct

from clients import get_database, get_qdrant_client
from domain.models import Branch, Coordinates
from services.embeddings.gemini_service import GeminiEmbeddingService
from utils.cache import (
    TTL_DEFAULT,
    get_branch_cache_key,
    get_cached,
    invalidate_branch_cache,
    invalidate_product_cache,
    set_cached,
    should_cache_result,
)


class BranchRepository:
    mongo_collection_name = "branches"
    qdrant_collection_name = "branches"

    # RAG fields stored in Qdrant
    rag_fields = {"name", "tipos"}

    # --- GET Methods (MongoDB) ---

    async def get_all(self) -> List[Branch]:
        """Get all branches from MongoDB with caching."""
        cache_key = get_branch_cache_key("all")
        cached = get_cached(cache_key)

        if cached is not None:
            return [self._dict_to_branch(b) for b in cached]

        try:
            print("→ Fetching all branches from MongoDB")
            db = get_database()
            cursor = db[self.mongo_collection_name].find()
            documents = await cursor.to_list(length=None)

            branches = [self._dict_to_branch(doc) for doc in documents]

            # Cache the results only if not too large
            if should_cache_result(branches):
                serialized = [b.model_dump() for b in branches]
                set_cached(cache_key, serialized, TTL_DEFAULT)
                print(f"✓ Cached {len(branches)} branches (get_all)")
            else:
                print(f"⚠ Skipped caching {len(branches)} branches (exceeds limit)")

            return branches

        except Exception as e:
            print(f"Error fetching all branches from MongoDB: {e}")
            return []

    async def get_by_id(self, branch_id: str) -> Optional[Branch]:
        """Get branch by ID from MongoDB with caching."""
        cache_key = get_branch_cache_key(f"id:{branch_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            return self._dict_to_branch(cached)

        try:
            print(f"→ Fetching branch {branch_id} from MongoDB")
            db = get_database()
            doc = await db[self.mongo_collection_name].find_one(
                {"_id": ObjectId(branch_id)}
            )

            if doc:
                branch = self._dict_to_branch(doc)
                # Cache the result
                set_cached(cache_key, branch.model_dump(), TTL_DEFAULT)
                return branch
            return None

        except Exception as e:
            print(f"Error fetching branch {branch_id} from MongoDB: {e}")
            return None

    async def get_by_ids(self, branch_ids: List[str]) -> List[Branch]:
        """Get branches by IDs from MongoDB with caching."""
        if not branch_ids:
            return []

        branch_ids = [str(branch_id) for branch_id in branch_ids]
        cache_key = get_branch_cache_key(f"ids:{','.join(sorted(branch_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [self._dict_to_branch(b) for b in cached]

        try:
            print(f"→ Fetching {len(branch_ids)} branches from MongoDB")
            db = get_database()
            object_ids = [ObjectId(bid) for bid in branch_ids]
            cursor = db[self.mongo_collection_name].find({"_id": {"$in": object_ids}})
            documents = await cursor.to_list(length=None)

            branches = [self._dict_to_branch(doc) for doc in documents]

            # Cache the results
            serialized = [b.model_dump() for b in branches]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return branches

        except Exception as e:
            print(f"Error fetching branches from MongoDB: {e}")
            return []

    async def get_by_business(self, business_id: str) -> List[Branch]:
        """Get branches by business ID from MongoDB."""
        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find(
                {"businessId": ObjectId(business_id)}
            )
            documents = await cursor.to_list(length=None)

            return [self._dict_to_branch(doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching branches by business from MongoDB: {e}")
            return []

    async def get_by_business_ids(self, business_ids: List[str]) -> List[Branch]:
        """Get branches by multiple business IDs from MongoDB."""
        if not business_ids:
            return []

        try:
            db = get_database()
            object_ids = [ObjectId(bid) for bid in business_ids]
            cursor = db[self.mongo_collection_name].find(
                {"businessId": {"$in": object_ids}}
            )
            documents = await cursor.to_list(length=None)

            return [self._dict_to_branch(doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching branches by business IDs from MongoDB: {e}")
            return []

    async def get_by_tipo(self, tipo: str) -> List[Branch]:
        """Get branches that have a specific tipo from MongoDB."""
        try:
            normalized_tipo = (tipo or "").strip()
            if not normalized_tipo:
                return []

            db = get_database()
            cursor = db[self.mongo_collection_name].find(
                {
                    "tipos": {
                        "$regex": f"^{re.escape(normalized_tipo)}$",
                        "$options": "i",
                    }
                }
            )
            documents = await cursor.to_list(length=None)

            return [self._dict_to_branch(doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching branches by tipo from MongoDB: {e}")
            return []

    async def get_ids_by_tipo(self, tipo: str) -> List[str]:
        """Get branch IDs that have a specific tipo from MongoDB."""
        try:
            normalized_tipo = (tipo or "").strip()
            if not normalized_tipo:
                return []

            db = get_database()
            cursor = db[self.mongo_collection_name].find(
                {
                    "tipos": {
                        "$regex": f"^{re.escape(normalized_tipo)}$",
                        "$options": "i",
                    }
                },
                {"_id": 1},  # Only return _id field
            )
            documents = await cursor.to_list(length=None)

            return [str(doc["_id"]) for doc in documents]

        except Exception as e:
            print(f"Error fetching branch IDs by tipo from MongoDB: {e}")
            return []

    # --- Search Method (Qdrant Vector Similarity) ---

    async def search(self, query: str, limit: int = 20) -> List[Branch]:
        """Search branches using Qdrant vector similarity."""
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
            print(f"Error searching branches in Qdrant: {e}")
            return []

    # --- Create Method (MongoDB + Qdrant) ---

    async def create(self, branch: Branch) -> Branch:
        """Create a new branch in both MongoDB and Qdrant."""
        try:
            db = get_database()

            # 1. Insert into MongoDB (complete document)
            doc = branch.model_dump(by_alias=True)
            # Convert coordinates to dict if it's a Pydantic model
            if hasattr(doc.get("coordinates"), "model_dump"):
                doc["coordinates"] = doc["coordinates"].model_dump()

            # Convert PyObjectId fields from strings to ObjectId for MongoDB
            doc["_id"] = ObjectId(doc["_id"])
            doc["businessId"] = ObjectId(doc["businessId"])
            doc["managerIds"] = [ObjectId(mid) for mid in doc["managerIds"]]

            # Handle paymentMethodIds - can be ObjectId or string
            doc["paymentMethodIds"] = [
                ObjectId(pid) if ObjectId.is_valid(pid) and len(pid) == 24 else pid
                for pid in doc["paymentMethodIds"]
            ]

            await db[self.mongo_collection_name].insert_one(doc)

            # 2. Insert into Qdrant (RAG fields + embedding)
            await self._upsert_to_qdrant(branch)

            # Invalidate cache for this business and all branches
            invalidate_branch_cache(business_id=branch.businessId)
            invalidate_branch_cache()  # Invalidate get_all cache

            return branch

        except Exception as e:
            print(f"Error creating branch: {e}")
            raise e

    # --- Update Method (MongoDB + Qdrant if RAG fields changed) ---

    async def update(self, branch_id: str, updates: Dict[str, Any]) -> Optional[Branch]:
        """Update a branch in MongoDB and Qdrant (if RAG fields changed)."""
        try:
            db = get_database()

            # Get current branch for cache invalidation
            current = await self.get_by_id(branch_id)
            if not current:
                return None

            # Convert coordinates if present
            if "coordinates" in updates and hasattr(
                updates["coordinates"], "model_dump"
            ):
                updates["coordinates"] = updates["coordinates"].model_dump()

            # Convert PyObjectId fields from strings to ObjectId for MongoDB
            if "businessId" in updates:
                updates["businessId"] = ObjectId(updates["businessId"])
            if "managerIds" in updates:
                updates["managerIds"] = [ObjectId(mid) for mid in updates["managerIds"]]
            if "paymentMethodIds" in updates:
                # Handle paymentMethodIds - can be ObjectId or string
                updates["paymentMethodIds"] = [
                    ObjectId(pid) if ObjectId.is_valid(pid) and len(pid) == 24 else pid
                    for pid in updates["paymentMethodIds"]
                ]

            # 1. Update MongoDB
            await db[self.mongo_collection_name].update_one(
                {"_id": ObjectId(branch_id)}, {"$set": updates}
            )

            # 2. If RAG fields changed, update Qdrant
            if self.rag_fields.intersection(updates.keys()):
                updated_branch = await self.get_by_id(branch_id)
                if updated_branch:
                    await self._upsert_to_qdrant(updated_branch)

            # Invalidate cache for this branch, its business, and all branches
            invalidate_branch_cache(branch_id=branch_id)
            business_id = updates.get("businessId", current.businessId)
            if business_id:
                invalidate_branch_cache(business_id=business_id)
            invalidate_branch_cache()  # Invalidate get_all cache

            # If branch has products, invalidate product cache too
            invalidate_product_cache(branch_id=branch_id)

            return await self.get_by_id(branch_id)

        except Exception as e:
            print(f"Error updating branch {branch_id}: {e}")
            raise e

    async def update_field(
        self, branch_id: str, field: str, value: Any
    ) -> Optional[Branch]:
        """Update a single field of a branch."""
        return await self.update(branch_id, {field: value})

    # --- Delete Method (MongoDB + Qdrant) ---

    async def delete(self, branch_id: str) -> bool:
        """Delete a branch from both MongoDB and Qdrant."""
        try:
            db = get_database()

            # Get branch for cache invalidation
            branch = await self.get_by_id(branch_id)
            business_id = branch.businessId if branch else None

            # 1. Delete from MongoDB
            result = await db[self.mongo_collection_name].delete_one(
                {"_id": ObjectId(branch_id)}
            )

            if result.deleted_count == 0:
                return False

            # 2. Delete from Qdrant
            await self._delete_from_qdrant(branch_id)

            # Invalidate cache
            invalidate_branch_cache(branch_id=branch_id)
            if business_id:
                invalidate_branch_cache(business_id=business_id)
            invalidate_branch_cache()  # Invalidate get_all cache
            invalidate_product_cache(branch_id=branch_id)

            return True

        except Exception as e:
            print(f"Error deleting branch {branch_id}: {e}")
            raise e

    # --- Wallet Methods (MongoDB) ---

    async def get_wallet(self, branch_id: str) -> Optional[Dict[str, float]]:
        """Get branch wallet balance."""
        branch = await self.get_by_id(branch_id)
        return branch.wallet if branch else None

    async def update_wallet(
        self, branch_id: str, currency: str, amount: float
    ) -> Optional[Branch]:
        """
        Update branch wallet balance for a specific currency using atomic $set.

        Args:
            branch_id: The branch ID
            currency: Currency type ('local' or 'usd')
            amount: New amount to set

        Returns:
            Updated branch or None
        """
        try:
            db = get_database()
            result = await db[self.mongo_collection_name].find_one_and_update(
                {"_id": ObjectId(branch_id)},
                {"$set": {f"wallet.{currency}": amount}},
                return_document=True,
            )
            if result:
                invalidate_branch_cache(branch_id=branch_id)
                invalidate_branch_cache()
                return self._dict_to_branch(result)
            return None
        except Exception as e:
            print(f"Error updating wallet for branch {branch_id}: {e}")
            return None

    async def increment_wallet(
        self, branch_id: str, currency: str, amount: float
    ) -> Optional[Branch]:
        """
        Increment branch wallet balance for a specific currency using atomic $inc.

        Args:
            branch_id: The branch ID
            currency: Currency type ('local' or 'usd')
            amount: Amount to increment (can be negative for decrement)

        Returns:
            Updated branch or None
        """
        try:
            db = get_database()
            result = await db[self.mongo_collection_name].find_one_and_update(
                {"_id": ObjectId(branch_id)},
                {"$inc": {f"wallet.{currency}": amount}},
                return_document=True,
            )
            if result:
                invalidate_branch_cache(branch_id=branch_id)
                invalidate_branch_cache()
                return self._dict_to_branch(result)
            return None
        except Exception as e:
            print(f"Error incrementing wallet for branch {branch_id}: {e}")
            return None

    async def update_wallet_status(
        self, branch_id: str, status: str
    ) -> Optional[Branch]:
        """
        Update branch wallet status.

        Args:
            branch_id: The branch ID
            status: New wallet status ('active', 'frozen', 'closed')

        Returns:
            Updated branch or None
        """
        return await self.update(branch_id, {"walletStatus": status})

    # --- Qdrant Helper Methods ---

    async def _upsert_to_qdrant(self, branch: Branch):
        """Upsert branch to Qdrant with RAG-only payload."""
        try:
            embedding_service = GeminiEmbeddingService()
            tipos_str = " ".join(branch.tipos or [])
            text_to_embed = f"{branch.name} {tipos_str}"
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()

            # First, try to find existing point
            existing = await self._find_qdrant_point(str(branch.id))

            # RAG-only payload
            payload = {
                "mongo_id": str(branch.id),
                "name": branch.name,
                "tipos": branch.tipos or [],
            }

            point_id = existing.id if existing else str(branch.id)
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
            print(f"Error upserting branch to Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _delete_from_qdrant(self, branch_id: str):
        """Delete branch from Qdrant by mongo_id."""
        try:
            qdrant_client = get_qdrant_client()

            # Find point by mongo_id
            existing = await self._find_qdrant_point(branch_id)
            if existing:
                await qdrant_client.delete(
                    collection_name=self.qdrant_collection_name,
                    points_selector=qdrant_models.PointIdsList(points=[existing.id]),
                )

        except Exception as e:
            print(f"Error deleting branch from Qdrant: {e}")
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
                            match=qdrant_models.MatchValue(value=mongo_id),
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

    # --- Helper Methods ---

    @staticmethod
    def _dict_to_branch(doc: Dict[str, Any]) -> Branch:
        """Convert a MongoDB document to a Branch model."""
        # Handle coordinates
        coords_data = doc.get("coordinates", {})
        if isinstance(coords_data, dict):
            coordinates = Coordinates(
                type=coords_data.get("type", "Point"),
                coordinates=coords_data.get("coordinates", [0.0, 0.0]),
            )
        else:
            coordinates = coords_data  # Already a Coordinates object

        # Build branch data
        branch_data = {**doc, "coordinates": coordinates}
        return Branch(**branch_data)
