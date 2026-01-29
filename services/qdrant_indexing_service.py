"""Service for indexing entities in Qdrant after creation in MongoDB."""
import logging
from typing import Optional, List
from qdrant_client.models import PointStruct
import uuid

from clients import get_qdrant_client
from services.embeddings.gemini_service import GeminiEmbeddingService
from models import Product, Branch, Business

logger = logging.getLogger(__name__)


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

            # Generate text for embedding
            embedding_text = f"{product.name}. {product.description or ''}"

            # Generate embedding using Gemini with RETRIEVAL_DOCUMENT task type
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create payload with MongoDB ID (flat structure)
            payload = {
                "mongo_id": product.id,
                "name": product.name,
                "price": product.price,
                "description": product.description or "",
            }

            # Create point
            point = PointStruct(
                id=str(uuid.uuid4()),  # Random UUID for Qdrant point ID
                vector=embedding,
                payload=payload
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="products",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Product indexed successfully: {product.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing product {product.name}: {e}")
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
            tipos_str = ", ".join(branch.tipos or [])
            embedding_text = f"{branch.name}. Tipos: {tipos_str}. {branch.address or ''}"

            # Generate embedding
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create payload with MongoDB ID (flat structure)
            payload = {
                "mongo_id": branch.id,
                "name": branch.name,
                "tipos": branch.tipos or [],
            }

            # Create point
            point = PointStruct(
                id=str(uuid.uuid4()),  # Random UUID for Qdrant point ID
                vector=embedding,
                payload=payload
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="branches",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Branch indexed successfully: {branch.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing branch {branch.name}: {e}")
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
            embedding_text = f"{business.name}. {business.description or ''}"

            # Generate embedding
            embedding = self.embedding_service.generate_embedding(
                embedding_text,
                task_type="RETRIEVAL_DOCUMENT"
            )

            # Create payload with MongoDB ID (flat structure)
            payload = {
                "mongo_id": business.id,
                "name": business.name,
                "description": business.description or "",
            }

            # Create point
            point = PointStruct(
                id=str(uuid.uuid4()),  # Random UUID for Qdrant point ID
                vector=embedding,
                payload=payload
            )

            # Upsert to Qdrant
            await qdrant_client.upsert(
                collection_name="businesses",
                points=[point]
            )

            logger.info(f"[Qdrant] ✓ Business indexed successfully: {business.name}")
            return True

        except Exception as e:
            logger.error(f"[Qdrant] ✗ Error indexing business {business.name}: {e}")
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
