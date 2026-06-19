"""Service for indexing entities in Qdrant after creation in MongoDB."""
import logging
import uuid
from typing import Optional, List
from qdrant_client.models import PointStruct

from clients import get_qdrant_client
from services.embeddings.gemini_service import GeminiEmbeddingService
from services.qdrant_payloads import (
    branch_embedding_text,
    branch_payload,
    business_embedding_text,
    business_payload,
    product_embedding_text,
    product_payload,
)
from domain.models import Product, Branch, Business

logger = logging.getLogger(__name__)

_UUID_NAMESPACE = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")


def _mongo_id_to_uuid(mongo_id: str) -> str:
    """Convert a MongoDB ObjectId string to a deterministic UUID."""
    return str(uuid.uuid5(_UUID_NAMESPACE, mongo_id))


class QdrantIndexingService:
    """Service for indexing MongoDB entities in Qdrant for vector search."""

    def __init__(self):
        """Initialize indexing service."""
        self._embedding_service = None
    
    @property
    def embedding_service(self):
        """Lazy initialization of embedding service."""
        if self._embedding_service is None:
            self._embedding_service = GeminiEmbeddingService()
        return self._embedding_service

    def _get_qdrant_client(self):
        """Get Qdrant client or return None if not available."""
        try:
            return get_qdrant_client()
        except RuntimeError:
            logger.warning("Qdrant client not available, skipping indexing")
            return None

    async def _resolve_category_name(self, product: Product):
        """Look up the product's category name to enrich the embedding text."""
        category_id = getattr(product, "categoryId", None)
        if not category_id:
            return None
        try:
            from repositories import product_categories_repo

            category = await product_categories_repo.get_by_id(str(category_id))
            return category.name if category else None
        except Exception as e:
            logger.debug(f"Could not resolve category {category_id}: {e}")
            return None

    async def index_product(self, product: Product) -> bool:
        """
        Index a product in Qdrant after it's created in MongoDB.

        Args:
            product: Product model instance with MongoDB ID

        Returns:
            bool: True if indexed successfully, False otherwise
        """
        qdrant_client = self._get_qdrant_client()
        if not qdrant_client:
            return False

        try:
            logger.info(f"[Qdrant] Indexing product: {product.name} (ID: {product.id})")

            # Generate text for embedding (enriched with category name)
            category_name = await self._resolve_category_name(product)
            embedding_text = product_embedding_text(product, category_name)

            # Generate embedding using Gemini with RETRIEVAL_DOCUMENT task type
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create point (UUID derived from mongo_id — Qdrant requires UUID or int)
            point = PointStruct(
                id=_mongo_id_to_uuid(str(product.id)),
                vector=embedding,
                payload=product_payload(product)
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="products",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Product indexed successfully: {product.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing product {product.name}: {type(e).__name__}: {str(e)}")
            logger.debug(f"Full traceback:", exc_info=True)
            return False

    async def index_branch(self, branch: Branch) -> bool:
        """
        Index a branch in Qdrant after it's created in MongoDB.

        Args:
            branch: Branch model instance with MongoDB ID

        Returns:
            bool: True if indexed successfully, False otherwise
        """
        qdrant_client = self._get_qdrant_client()
        if not qdrant_client:
            return False

        try:
            logger.info(f"[Qdrant] Indexing branch: {branch.name} (ID: {branch.id})")

            # Generate text for embedding
            embedding_text = branch_embedding_text(branch)

            # Generate embedding
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create point (UUID derived from mongo_id — Qdrant requires UUID or int)
            point = PointStruct(
                id=_mongo_id_to_uuid(str(branch.id)),
                vector=embedding,
                payload=branch_payload(branch)
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="branches",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Branch indexed successfully: {branch.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing branch {branch.name}: {type(e).__name__}: {str(e)}")
            logger.debug(f"Full traceback:", exc_info=True)
            return False

    async def index_business(self, business: Business) -> bool:
        """
        Index a business in Qdrant after it's created in MongoDB.

        Args:
            business: Business model instance with MongoDB ID

        Returns:
            bool: True if indexed successfully, False otherwise
        """
        qdrant_client = self._get_qdrant_client()
        if not qdrant_client:
            return False

        try:
            logger.info(f"[Qdrant] Indexing business: {business.name} (ID: {business.id})")

            # Generate text for embedding
            embedding_text = business_embedding_text(business)

            # Generate embedding
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create point (UUID derived from mongo_id — Qdrant requires UUID or int)
            point = PointStruct(
                id=_mongo_id_to_uuid(str(business.id)),
                vector=embedding,
                payload=business_payload(business)
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="businesses",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Business indexed successfully: {business.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing business {business.name}: {type(e).__name__}: {str(e)}")
            logger.debug(f"Full traceback:", exc_info=True)
            return False

    async def delete_product(self, product_id: str) -> bool:
        """
        Delete a product from Qdrant by mongo_id.

        Args:
            product_id: MongoDB product ID

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        qdrant_client = self._get_qdrant_client()
        if not qdrant_client:
            return False

        try:
            logger.info(f"[Qdrant] Deleting product with mongo_id: {product_id}")

            # Search for points with this mongo_id
            # Note: This requires scrolling through points or using a filter
            # For simplicity, we'll skip deletion or implement later
            # Qdrant doesn't support easy deletion by payload field

            logger.warning(f"[Qdrant] Product deletion not fully implemented yet")
            return False

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error deleting product: {e}")
            return False


# Singleton instance
qdrant_indexing_service = QdrantIndexingService()
