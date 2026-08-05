"""Product repository for database operations.

Hybrid repository pattern:
- GET operations: MongoDB (source of truth for complete data)
- Search: Qdrant vector similarity (semantic search)
- Create/Update/Delete: Sync both databases
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import uuid

logger = logging.getLogger(__name__)

from bson import ObjectId
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import PointStruct

_UUID_NAMESPACE = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")


def _mongo_id_to_uuid(mongo_id: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, mongo_id))

from clients import delete_by_mongo_id, get_database, get_qdrant_client
from domain.models import Product
from services.embeddings.gemini_service import GeminiEmbeddingService
from services.qdrant_payloads import (
    PRODUCT_PAYLOAD_FIELDS,
    PRODUCT_TEXT_FIELDS,
    product_embedding_text,
    product_payload,
)
from utils.cache import (
    invalidate_product_cache,
)


class ProductRepository:
    mongo_collection_name = "products"
    qdrant_collection_name = "products"

    @staticmethod
    def _to_object_id(value: Any) -> Any:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(str(value))
        except Exception:
            return value

    @classmethod
    def _to_object_ids(cls, values: List[Any]) -> List[Any]:
        return [cls._to_object_id(value) for value in values]

    @staticmethod
    def _deserialize_products(
        documents: List[Dict[str, Any]], context: str = ""
    ) -> List[Product]:
        """Deserialize Mongo documents to Product, skipping only invalid rows."""
        products: List[Product] = []
        for doc in documents:
            try:
                products.append(Product(**doc))
            except Exception as parse_error:
                doc_id = doc.get("_id")
                branch_id = doc.get("branchId")
                logger.warning(
                    f"Skipping invalid product doc in {context} "
                    f"(id={doc_id}, branchId={branch_id}): {parse_error}"
                )
        return products

    # --- GET Methods (MongoDB) ---

    DEFAULT_LIMIT = 5000

    async def get_all(self, limit: Optional[int] = None) -> List[Product]:
        """Get all products from MongoDB.

        Args:
            limit: Maximum number of products to return. Defaults to DEFAULT_LIMIT.
        """
        effective_limit = limit if limit is not None else self.DEFAULT_LIMIT

        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find().limit(effective_limit)
            documents = await cursor.to_list(length=effective_limit)

            products = [Product(**doc) for doc in documents]
            return products

        except Exception as e:
            logger.error(f"Error fetching all products from MongoDB: {e}")
            return []

    async def get_by_id(self, product_id: str) -> Optional[Product]:
        """Get product by ID from MongoDB."""
        try:
            db = get_database()
            doc = await db[self.mongo_collection_name].find_one(
                {"_id": self._to_object_id(product_id)}
            )

            if doc:
                return Product(**doc)
            return None

        except Exception as e:
            logger.error(f"Error fetching product {product_id} from MongoDB: {e}")
            return None

    async def has_other_products_with_image(
        self,
        image_path: str,
        exclude_product_id: Optional[str] = None,
    ) -> bool:
        """Check whether another product references the same image path."""
        if not image_path:
            return False

        try:
            db = get_database()
            query: Dict[str, Any] = {"image": image_path}

            if exclude_product_id:
                query["_id"] = {"$ne": self._to_object_id(exclude_product_id)}

            doc = await db[self.mongo_collection_name].find_one(query, {"_id": 1})
            return doc is not None
        except Exception as e:
            logger.error(f"Error checking shared product image {image_path}: {e}")
            # Be conservative: if we cannot verify, assume it's shared.
            return True

    async def get_by_ids(self, product_ids: List[str]) -> List[Product]:
        """Get products by IDs from MongoDB."""
        if not product_ids:
            return []

        ids = [str(x) for x in product_ids]

        try:
            db = get_database()
            object_ids = self._to_object_ids(ids)
            cursor = db[self.mongo_collection_name].find({"_id": {"$in": object_ids}})
            documents = await cursor.to_list(length=None)

            products = [Product(**doc) for doc in documents]
            return products

        except Exception as e:
            logger.error(f"Error fetching products from MongoDB: {e}")
            return []

    async def get_by_branch(self, branch_id: str) -> List[Product]:
        """Get products by branch ID from MongoDB."""
        normalized_branch_id = str(branch_id).strip()

        try:
            db = get_database()

            branch_oid = self._to_object_id(normalized_branch_id)

            # Support datasets where branchId may be stored as ObjectId or string.
            cursor = db[self.mongo_collection_name].find(
                {
                    "$or": [
                        {"branchId": branch_oid},
                        {"branchId": normalized_branch_id},
                    ]
                }
            )
            documents = await cursor.to_list(length=None)

            products = self._deserialize_products(
                documents, context=f"get_by_branch:{normalized_branch_id}"
            )

            return products

        except Exception as e:
            logger.error(f"Error fetching products by branch from MongoDB: {e}")
            return []

    async def get_by_branch_ids(self, branch_ids: List[Any]) -> List[Product]:
        """Get products from multiple branches using MongoDB.

        Args:
            branch_ids: List of branch IDs (can be strings or ObjectIds)
        """
        if not branch_ids:
            return []

        # Convert to strings (handles both str and ObjectId)
        ids = [str(x).strip() for x in branch_ids]

        try:
            db = get_database()
            converted_ids = self._to_object_ids(branch_ids)
            object_ids = [oid for oid in converted_ids if isinstance(oid, ObjectId)]

            query_conditions: List[Dict[str, Any]] = []
            if object_ids:
                query_conditions.append({"branchId": {"$in": object_ids}})
            if ids:
                query_conditions.append({"branchId": {"$in": ids}})

            if not query_conditions:
                return []

            query: Dict[str, Any]
            if len(query_conditions) == 1:
                query = query_conditions[0]
            else:
                query = {"$or": query_conditions}

            cursor = db[self.mongo_collection_name].find(query)
            documents = await cursor.to_list(length=None)

            products = self._deserialize_products(
                documents, context="get_by_branch_ids"
            )

            return products

        except Exception as e:
            logger.error(f"Error fetching products by branch IDs from MongoDB: {e}")
            return []

    async def get_available(self) -> List[Product]:
        """Get available products from MongoDB."""
        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find({"availability": True})
            documents = await cursor.to_list(length=None)

            return [Product(**doc) for doc in documents]

        except Exception as e:
            logger.error(f"Error fetching available products from MongoDB: {e}")
            return []

    async def get_by_category(self, category_id: str) -> List[Product]:
        """Get products by category ID from MongoDB."""
        try:
            db = get_database()
            cursor = db[self.mongo_collection_name].find(
                {"categoryId": self._to_object_id(category_id)}
            )
            documents = await cursor.to_list(length=None)

            return [Product(**doc) for doc in documents]

        except Exception as e:
            logger.error(f"Error fetching products by category from MongoDB: {e}")
            return []

    async def get_distinct_branch_ids_by_category(self, category_id: str) -> set:
        """Get distinct branch IDs that have products in the given category.

        Uses MongoDB distinct() to avoid downloading full documents.
        """
        try:
            db = get_database()
            branch_ids = await db[self.mongo_collection_name].distinct(
                "branchId", {"categoryId": self._to_object_id(category_id)}
            )
            return {str(bid) for bid in branch_ids}
        except Exception as e:
            logger.error(f"Error fetching distinct branch IDs by category: {e}")
            return set()

    # --- Search Method (Qdrant Vector Similarity) ---

    async def search(self, query: str, limit: int = 20) -> List[Product]:
        """Search products using Qdrant vector similarity."""
        try:
            # Generate embedding for query
            embedding_service = GeminiEmbeddingService()
            query_vector = await asyncio.to_thread(
                embedding_service.generate_embedding, query
            )

            qdrant_client = get_qdrant_client()

            # Vector similarity search (query_points replaces deprecated .search() in 1.16+)
            response = await qdrant_client.query_points(
                collection_name=self.qdrant_collection_name,
                query=query_vector,
                limit=limit,
            )
            results = response.points if hasattr(response, "points") else response

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
            logger.warning(f"Error searching products in Qdrant: {e}")
            return []

    # --- Create Method (MongoDB + Qdrant) ---

    async def create(self, product: Product) -> Product:
        """Create a new product in both MongoDB and Qdrant."""
        try:
            db = get_database()

            # 1. Insert into MongoDB (complete document)
            doc = product.model_dump(by_alias=True)
            doc["_id"] = self._to_object_id(doc.get("_id"))
            doc["branchId"] = self._to_object_id(doc.get("branchId"))
            if doc.get("categoryId") is not None:
                doc["categoryId"] = self._to_object_id(doc.get("categoryId"))
            # Convert variantListIds to ObjectIds
            if doc.get("variantListIds"):
                doc["variantListIds"] = self._to_object_ids(doc.get("variantListIds"))
            await db[self.mongo_collection_name].insert_one(doc)

            # 2. Insert into Qdrant (RAG fields + embedding)
            await self._upsert_to_qdrant(product)

            # Invalidate cache for this branch and all products
            invalidate_product_cache(branch_id=product.branchId)
            invalidate_product_cache()  # Invalidate get_all cache

            return product

        except Exception as e:
            logger.error(f"Error creating product: {e}")
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
            normalized_updates = dict(updates)
            if "branchId" in normalized_updates:
                normalized_updates["branchId"] = self._to_object_id(
                    normalized_updates["branchId"]
                )
            if (
                "categoryId" in normalized_updates
                and normalized_updates["categoryId"] is not None
            ):
                normalized_updates["categoryId"] = self._to_object_id(
                    normalized_updates["categoryId"]
                )
            # Convert variantListIds to ObjectIds
            if "variantListIds" in normalized_updates:
                normalized_updates["variantListIds"] = self._to_object_ids(
                    normalized_updates["variantListIds"]
                )

            normalized_updates["updatedAt"] = datetime.now()
            await db[self.mongo_collection_name].update_one(
                {"_id": self._to_object_id(product_id)}, {"$set": normalized_updates}
            )

            # 2. Sync Qdrant. Re-embed only when text fields changed; otherwise
            #    do a cheap payload-only update (keeps availability/category/price
            #    filterable without burning a Gemini call).
            changed = set(normalized_updates.keys())
            if changed & PRODUCT_TEXT_FIELDS:
                updated_product = await self.get_by_id(product_id)
                if updated_product:
                    await self._upsert_to_qdrant(updated_product)
            elif changed & PRODUCT_PAYLOAD_FIELDS:
                updated_product = await self.get_by_id(product_id)
                if updated_product:
                    await self._set_qdrant_payload(updated_product)

            # Invalidate cache
            branch_id = normalized_updates.get("branchId", current.branchId)
            invalidate_product_cache(branch_id=str(branch_id))
            if current.branchId != branch_id:
                invalidate_product_cache(branch_id=str(current.branchId))
            invalidate_product_cache()  # Invalidate get_all cache

            return await self.get_by_id(product_id)

        except Exception as e:
            logger.error(f"Error updating product {product_id}: {e}")
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
                {"_id": self._to_object_id(product_id)}
            )

            if result.deleted_count == 0:
                return False

            # 2. Delete from Qdrant
            await self._delete_from_qdrant(product_id)

            # Invalidate cache
            if branch_id:
                invalidate_product_cache(branch_id=str(branch_id))
            invalidate_product_cache()  # Invalidate get_all cache

            return True

        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return False

    # --- Qdrant Helper Methods ---

    async def _resolve_category_name(self, product: Product) -> Optional[str]:
        """Look up the product's category name to enrich the embedding text."""
        category_id = getattr(product, "categoryId", None)
        if not category_id:
            return None
        try:
            from repositories import product_categories_repo

            category = await product_categories_repo.get_by_id(str(category_id))
            return category.name if category else None
        except Exception as e:
            print(f"Could not resolve category {category_id} for embedding: {e}")
            return None

    async def _upsert_to_qdrant(self, product: Product):
        """Upsert product to Qdrant with the enriched payload + fresh embedding."""
        try:
            embedding_service = GeminiEmbeddingService()
            category_name = await self._resolve_category_name(product)
            text_to_embed = product_embedding_text(product, category_name)
            embedding = embedding_service.generate_embedding(text_to_embed)

            qdrant_client = get_qdrant_client()

            # First, try to find existing point (reuses legacy point ids if any)
            mongo_id = str(product.id)
            existing = await self._find_qdrant_point(mongo_id)

            point_id = existing.id if existing else _mongo_id_to_uuid(mongo_id)
            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=product_payload(product),
            )

            await qdrant_client.upsert(
                collection_name=self.qdrant_collection_name,
                points=[point],
            )

        except Exception as e:
            logger.warning(f"Error upserting product to Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _set_qdrant_payload(self, product: Product):
        """Update only the payload of an existing point (no re-embedding)."""
        try:
            qdrant_client = get_qdrant_client()
            mongo_id = str(product.id)
            existing = await self._find_qdrant_point(mongo_id)
            point_id = existing.id if existing else _mongo_id_to_uuid(mongo_id)
            await qdrant_client.set_payload(
                collection_name=self.qdrant_collection_name,
                payload=product_payload(product),
                points=[point_id],
            )
        except Exception as e:
            print(f"Error setting product payload in Qdrant: {e}")
            # Don't raise - MongoDB is the source of truth

    async def _delete_from_qdrant(self, product_id: str):
        """Delete product from Qdrant (all points sharing this mongo_id)."""
        await delete_by_mongo_id(self.qdrant_collection_name, str(product_id))

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
            logger.warning(f"Error finding Qdrant point: {e}")
            return None

    async def remove_variant_list_from_products(self, variant_list_id: str) -> int:
        """Remove a variant list ID from all products that reference it."""
        db = get_database()
        oid = self._to_object_id(variant_list_id)
        result = await db[self.mongo_collection_name].update_many(
            {"variantListIds": oid},
            {"$pull": {"variantListIds": oid}},
        )
        if result.modified_count > 0:
            invalidate_product_cache()
        return result.modified_count

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

        # Only include available products in the feed
        products = [p for p in products if getattr(p, "availability", False)]

        # If no category filtering, return all products
        if not apply_category_filter:
            return products

        # Apply feed category filtering
        from repositories import product_categories_repo

        # Batch-fetch all unique category IDs in a single query
        unique_category_ids = list({p.categoryId for p in products if p.categoryId})
        category_map: dict = {}
        if unique_category_ids:
            try:
                fetched = await product_categories_repo.get_by_ids(unique_category_ids)
                category_map = {str(c.id): c for c in fetched}
            except Exception as e:
                logger.warning(f"Error batch-fetching categories: {e}")

        filtered_products = []
        for product in products:
            if not product.categoryId:
                if not requested_branch_tipo:
                    filtered_products.append(product)
                continue

            category = category_map.get(str(product.categoryId))
            if not category:
                logger.warning(
                    f"Product {product.id} ({product.name}) has invalid categoryId: {product.categoryId}"
                )
                if not requested_branch_tipo:
                    filtered_products.append(product)
                continue

            if requested_branch_tipo:
                if category.branchType == requested_branch_tipo:
                    filtered_products.append(product)
            else:
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
            logger.error(f"Error fetching recent products: {e}")
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
        timestamps = [
            (str(p.id), (now - p.createdAt).total_seconds()) for p in products
        ]

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
