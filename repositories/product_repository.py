"""Product repository for database operations.

Hybrid repository pattern:
- GET operations: MongoDB (source of truth for complete data)
- Search: Qdrant vector similarity (semantic search)
- Create/Update/Delete: Sync both databases
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct

from clients import get_database, get_qdrant_client
from domain.models import Product
from services.embeddings.gemini_service import GeminiEmbeddingService
from utils.cache import (
    TTL_DEFAULT,
    get_cached,
    get_product_cache_key,
    invalidate_product_cache,
    set_cached,
    should_cache_result,
)


class ProductRepository:
    mongo_collection_name = "products"
    qdrant_collection_name = "products"

    # RAG fields stored in Qdrant
    rag_fields = {"name", "price", "description"}

    # --- GET Methods (MongoDB) ---

    DEFAULT_LIMIT = 5000

    async def get_all(self, limit: Optional[int] = None) -> List[Product]:
        """Get all products from MongoDB with caching.

        Args:
            limit: Maximum number of products to return. Defaults to DEFAULT_LIMIT.
        """
        effective_limit = limit if limit is not None else self.DEFAULT_LIMIT
        cache_key = get_product_cache_key(f"all:limit:{effective_limit}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Product(**p) for p in cached]

        try:
            print(f"→ Fetching products from MongoDB (limit={effective_limit})")
            db = get_database()
            cursor = db[self.mongo_collection_name].find().limit(effective_limit)
            documents = await cursor.to_list(length=effective_limit)

            products = [Product(**doc) for doc in documents]

            # Cache the results only if not too large
            if should_cache_result(products):
                serialized = [p.model_dump() for p in products]
                set_cached(cache_key, serialized, TTL_DEFAULT)
                print(f"✓ Cached {len(products)} products (get_all)")
            else:
                print(f"⚠ Skipped caching {len(products)} products (exceeds limit)")

            return products

        except Exception as e:
            print(f"Error fetching all products from MongoDB: {e}")
            return []

    async def get_by_id(self, product_id: str) -> Optional[Product]:
        """Get product by ID from MongoDB."""
        try:
            db = get_database()
            doc = await db[self.mongo_collection_name].find_one({"_id": product_id})

            if doc:
                return Product(**doc)
            return None

        except Exception as e:
            print(f"Error fetching product {product_id} from MongoDB: {e}")
            return None

    async def get_by_ids(self, product_ids: List[str]) -> List[Product]:
        """Get products by IDs from MongoDB with caching."""
        if not product_ids:
            return []

        cache_key = get_product_cache_key(f"ids:{','.join(sorted(product_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Product(**p) for p in cached]

        try:
            print(f"→ Fetching {len(product_ids)} products by IDs from MongoDB")
            db = get_database()
            cursor = db[self.mongo_collection_name].find({"_id": {"$in": product_ids}})
            documents = await cursor.to_list(length=None)

            products = [Product(**doc) for doc in documents]

            # Cache the results
            serialized = [p.model_dump() for p in products]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return products

        except Exception as e:
            print(f"Error fetching products from MongoDB: {e}")
            return []

    async def get_by_branch(self, branch_id: str) -> List[Product]:
        """Get products by branch ID from MongoDB with caching."""
        cache_key = get_product_cache_key(f"branch:{branch_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Product(**p) for p in cached]

        try:
            print(f"→ Fetching products for branch {branch_id} from MongoDB")
            db = get_database()
            cursor = db[self.mongo_collection_name].find({"branchId": branch_id})
            documents = await cursor.to_list(length=None)

            products = [Product(**doc) for doc in documents]

            # Cache the results
            serialized = [p.model_dump() for p in products]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return products

        except Exception as e:
            print(f"Error fetching products by branch from MongoDB: {e}")
            return []

    async def get_by_branch_ids(self, branch_ids: List[str]) -> List[Product]:
        """Get products from multiple branches using MongoDB."""
        if not branch_ids:
            return []

        cache_key = get_product_cache_key(f"branch_ids:{','.join(sorted(branch_ids))}")
        cached = get_cached(cache_key)

        if cached is not None:
            return [Product(**p) for p in cached]

        try:
            print(f"→ Fetching products for {len(branch_ids)} branches from MongoDB")
            db = get_database()
            cursor = db[self.mongo_collection_name].find(
                {"branchId": {"$in": branch_ids}}
            )
            documents = await cursor.to_list(length=None)

            products = [Product(**doc) for doc in documents]

            # Cache the results
            serialized = [p.model_dump() for p in products]
            set_cached(cache_key, serialized, TTL_DEFAULT)

            return products

        except Exception as e:
            print(f"Error fetching products by branch IDs from MongoDB: {e}")
            return []

    async def get_available(self) -> List[Product]:
        """Get available products from MongoDB."""
        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find({"availability": True})
            documents = await cursor.to_list(length=None)

            return [Product(**doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching available products from MongoDB: {e}")
            return []

    async def get_by_category(self, category_id: str) -> List[Product]:
        """Get products by category ID from MongoDB."""
        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find({"categoryId": category_id})
            documents = await cursor.to_list(length=None)

            return [Product(**doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching products by category from MongoDB: {e}")
            return []

    async def get_distinct_branch_ids_by_category(self, category_id: str) -> set:
        """Get distinct branch IDs that have products in the given category.

        Uses MongoDB distinct() to avoid downloading full documents.
        """
        try:
            db = get_database()
            branch_ids = await db[self.mongo_collection_name].distinct(
                "branchId", {"categoryId": category_id}
            )
            return set(branch_ids)
        except Exception as e:
            print(f"Error fetching distinct branch IDs by category: {e}")
            return set()

    # --- Search Method (Qdrant Vector Similarity) ---

    async def search(self, query: str, limit: int = 20) -> List[Product]:
        """Search products using Qdrant vector similarity."""
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
            print(f"Error searching products in Qdrant: {e}")
            return []

    # --- Create Method (MongoDB + Qdrant) ---

    async def create(self, product: Product) -> Product:
        """Create a new product in both MongoDB and Qdrant."""
        try:
            db = get_database()

            # 1. Insert into MongoDB (complete document)
            doc = product.model_dump(by_alias=True)
            await db[self.mongo_collection_name].insert_one(doc)

            # 2. Insert into Qdrant (RAG fields + embedding)
            await self._upsert_to_qdrant(product)

            # Invalidate cache for this branch and all products
            invalidate_product_cache(branch_id=product.branchId)
            invalidate_product_cache()  # Invalidate get_all cache

            return product

        except Exception as e:
            print(f"Error creating product: {e}")
            raise e

    # --- Update Method (MongoDB + Qdrant if RAG fields changed) ---

    async def update(
        self, product_id: str, updates: Dict[str, Any]
    ) -> Optional[Product]:
        """Update a product in MongoDB and Qdrant (if RAG fields changed)."""
        try:
            db = get_database()

            # Get current product for branch_id (for cache invalidation)
            current = await self.get_by_id(product_id)
            if not current:
                return None

            # 1. Update MongoDB
            await db[self.mongo_collection_name].update_one(
                {"_id": product_id}, {"$set": updates}
            )

            # 2. If RAG fields changed, update Qdrant
            if self.rag_fields.intersection(updates.keys()):
                updated_product = await self.get_by_id(product_id)
                if updated_product:
                    await self._upsert_to_qdrant(updated_product)

            # Invalidate cache
            branch_id = updates.get("branchId", current.branchId)
            invalidate_product_cache(branch_id=branch_id)
            if current.branchId != branch_id:
                invalidate_product_cache(branch_id=current.branchId)
            invalidate_product_cache()  # Invalidate get_all cache

            return await self.get_by_id(product_id)

        except Exception as e:
            print(f"Error updating product {product_id}: {e}")
            raise e

    async def update_field(
        self, product_id: str, field: str, value: Any
    ) -> Optional[Product]:
        """Update a single field of a product."""
        return await self.update(product_id, {field: value})

    # --- Delete Method (MongoDB + Qdrant) ---

    async def delete(self, product_id: str) -> bool:
        """Delete a product from both MongoDB and Qdrant."""
        try:
            db = get_database()

            # Get product for cache invalidation
            product = await self.get_by_id(product_id)
            branch_id = product.branchId if product else None

            # 1. Delete from MongoDB
            result = await db[self.mongo_collection_name].delete_one(
                {"_id": product_id}
            )

            if result.deleted_count == 0:
                return False

            # 2. Delete from Qdrant
            await self._delete_from_qdrant(product_id)

            # Invalidate cache
            if branch_id:
                invalidate_product_cache(branch_id=branch_id)
            invalidate_product_cache()  # Invalidate get_all cache

            return True

        except Exception as e:
            print(f"Error deleting product {product_id}: {e}")
            return False

    # --- Qdrant Helper Methods ---

    async def _upsert_to_qdrant(self, product: Product):
        """Upsert product to Qdrant with RAG-only payload."""
        try:
            embedding_service = GeminiEmbeddingService()
            text_to_embed = f"{product.name} {product.description or ''}"
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()

            # First, try to find existing point
            existing = await self._find_qdrant_point(product.id)

            # RAG-only payload
            payload = {
                "mongo_id": product.id,
                "name": product.name,
                "price": product.price,
                "description": product.description,
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
            print(f"Error upserting product to Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _delete_from_qdrant(self, product_id: str):
        """Delete product from Qdrant by mongo_id."""
        try:
            qdrant_client = get_qdrant_client()

            # Find point by mongo_id
            existing = await self._find_qdrant_point(product_id)
            if existing:
                await qdrant_client.delete(
                    collection_name=self.qdrant_collection_name,
                    points_selector=qdrant_models.PointIdsList(points=[existing.id]),
                )

        except Exception as e:
            print(f"Error deleting product from Qdrant: {e}")
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

    # --- Feed Products Method ---

    async def get_feed_products(
        self,
        branch_ids: Optional[List[str]] = None,
        apply_category_filter: bool = True,
        requested_branch_tipo: Optional[str] = None,
    ) -> List[Product]:
        """
        Get products for the feed with category filtering.

        Feed filtering rules:
        - When viewing a specific branch: show ALL products (apply_category_filter=False)
        - When viewing feed by branchTipo: only show products whose category matches the requested tipo
        - Products without category are included only if no specific tipo is requested

        Args:
            branch_ids: List of branch IDs to get products from (None = all branches)
            apply_category_filter: Whether to apply feed category filtering rules
            requested_branch_tipo: The branch type being requested (e.g., "restaurante", "dulceria")

        Returns:
            List of filtered products
        """
        # Get products
        if branch_ids:
            products = await self.get_by_branch_ids(branch_ids)
        else:
            products = await self.get_all()

        # If no category filtering, return all products
        if not apply_category_filter:
            return products

        # Apply feed category filtering
        from repositories import product_categories_repo

        filtered_products = []

        for product in products:
            # Handle products without category
            if not product.categoryId:
                # Only include if no specific tipo is requested
                if not requested_branch_tipo:
                    filtered_products.append(product)
                continue

            # Get product category
            category = await product_categories_repo.get_by_id(product.categoryId)
            if not category:
                # If category not found, include only if no specific tipo requested
                if not requested_branch_tipo:
                    filtered_products.append(product)
                continue

            # If a specific branchTipo is requested, only show products
            # whose category matches that tipo
            if requested_branch_tipo:
                if category.branchType == requested_branch_tipo:
                    filtered_products.append(product)
            else:
                # No specific tipo requested - include all products with valid categories
                filtered_products.append(product)

        return filtered_products

    # --- Freshness Methods for Feed ---

    async def get_recent_products(
        self, days: int = 30, limit: int = 100
    ) -> List[Product]:
        """
        Get products created recently, ordered by createdAt DESC.

        Args:
            days: Number of days to look back (default 30)
            limit: Maximum number of products to return (default 100)

        Returns:
            List of recently created products
        """
        from datetime import timedelta

        try:
            db = get_database()
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            cursor = (
                db[self.mongo_collection_name]
                .find({"createdAt": {"$gte": cutoff_date}})
                .sort("createdAt", -1)
                .limit(limit)
            )

            documents = await cursor.to_list(length=limit)
            return [Product(**doc) for doc in documents]

        except Exception as e:
            print(f"Error fetching recent products: {e}")
            return []

    def calculate_freshness_scores(self, products: List[Product]) -> Dict[str, float]:
        """
        Calculate freshness scores (0-1) based on createdAt.
        More recent products = higher score.

        Args:
            products: List of products to score

        Returns:
            Dict[product_id: freshness_score]
        """
        if not products:
            return {}

        # Find oldest and newest products
        now = datetime.utcnow()
        timestamps = [(p.id, (now - p.createdAt).total_seconds()) for p in products]

        if not timestamps:
            return {}

        # Get min and max age in seconds
        max_age = max(age for _, age in timestamps)
        min_age = min(age for _, age in timestamps)

        # Avoid division by zero
        if max_age == min_age:
            return {pid: 1.0 for pid, _ in timestamps}

        # Normalize: newer products get higher scores
        # score = 1 - (age - min_age) / (max_age - min_age)
        scores = {}
        for pid, age in timestamps:
            normalized_age = (age - min_age) / (max_age - min_age)
            scores[pid] = 1.0 - normalized_age

        return scores
