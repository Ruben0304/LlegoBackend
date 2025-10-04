"""Vector search service using Qdrant."""
from typing import List, Optional
from qdrant_client.models import ScoredPoint

from clients import get_qdrant_client
from services.embeddings.gemini_service import GeminiEmbeddingService


class VectorSearchService:
    """Service for performing vector similarity searches in Qdrant."""

    def __init__(self):
        """Initialize vector search service."""
        self.qdrant_client = get_qdrant_client()
        self.embedding_service = GeminiEmbeddingService()

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[str]:
        """
        Search products using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.60)

        Returns:
            List of product IDs (MongoDB ObjectIDs) ordered by relevance
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        # embedding generation may be synchronous (Gemini client used synchronously),
        # keep as-is but allow future async implementations.
        query_embedding = self.embedding_service.generate_embedding(
            query,
            task_type="RETRIEVAL_QUERY"
        )

        # Search in Qdrant with minimum score threshold
        search_params = {
            "collection_name": "products",
            "query_vector": query_embedding,
            "limit": limit,
            "score_threshold": score_threshold if score_threshold is not None else 0.60
        }

        # qdrant client is AsyncQdrantClient; its search method is a coroutine and must be awaited
        results: List[ScoredPoint] = await self.qdrant_client.search(**search_params)

        print(f"Vector search for '{query}' returned {len(results)} results (threshold: {search_params['score_threshold']})")
        for r in results:
            print(f"  - Score: {r.score}, ID: {r.payload.get('id')}")

        # Extract MongoDB IDs from payload
        return [point.payload["id"] for point in results]

    async def search_branches(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[str]:
        """
        Search branches using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.55)

        Returns:
            List of branch IDs (MongoDB ObjectIDs) ordered by relevance
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        # embedding generation may be synchronous (Gemini client used synchronously),
        # keep as-is but allow future async implementations.
        query_embedding = self.embedding_service.generate_embedding(
            query,
            task_type="RETRIEVAL_QUERY"
        )

        # Search in Qdrant with minimum score threshold
        search_params = {
            "collection_name": "branches",
            "query_vector": query_embedding,
            "limit": limit,
            "score_threshold": score_threshold if score_threshold is not None else 0.55
        }

        # qdrant client is AsyncQdrantClient; its search method is a coroutine and must be awaited
        results: List[ScoredPoint] = await self.qdrant_client.search(**search_params)

        print(f"Vector search for '{query}' returned {len(results)} results (threshold: {search_params['score_threshold']})")
        for r in results:
            print(f"  - Score: {r.score}, ID: {r.payload.get('id')}")

        # Extract MongoDB IDs from payload
        return [point.payload["id"] for point in results]
