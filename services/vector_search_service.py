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

        # Search in Qdrant with minimum score threshold using query_points (v1.10+)
        threshold = score_threshold if score_threshold is not None else 0.60
        response = await self.qdrant_client.query_points(
            collection_name="products",
            query=query_embedding,
            limit=limit,
            score_threshold=threshold
        )

        # query_points returns a QueryResponse object with .points attribute
        results = response.points if hasattr(response, 'points') else response

        print(f"Vector search for '{query}' returned {len(results)} results (threshold: {threshold})")
        for r in results:
            # Handle both old (with metadata wrapper) and new (flat) structures
            mongo_id = r.payload.get('mongo_id') or r.payload.get('metadata', {}).get('mongo_id')
            print(f"  - Score: {r.score}, ID: {mongo_id}")

        # Extract MongoDB IDs from payload (handle both old and new structures)
        mongo_ids = []
        for point in results:
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = point.payload.get("mongo_id") or point.payload.get("metadata", {}).get("mongo_id")
            if mongo_id:
                mongo_ids.append(mongo_id)
        return mongo_ids

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

        # Search in Qdrant with minimum score threshold using query_points (v1.10+)
        threshold = score_threshold if score_threshold is not None else 0.55
        response = await self.qdrant_client.query_points(
            collection_name="branches",
            query=query_embedding,
            limit=limit,
            score_threshold=threshold
        )

        # query_points returns a QueryResponse object with .points attribute
        results = response.points if hasattr(response, 'points') else response

        print(f"Vector search for '{query}' returned {len(results)} results (threshold: {threshold})")
        for r in results:
            # Handle both old (with metadata wrapper) and new (flat) structures
            mongo_id = r.payload.get('mongo_id') or r.payload.get('metadata', {}).get('mongo_id')
            print(f"  - Score: {r.score}, ID: {mongo_id}")

        # Extract MongoDB IDs from payload (handle both old and new structures)
        mongo_ids = []
        for point in results:
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = point.payload.get("mongo_id") or point.payload.get("metadata", {}).get("mongo_id")
            if mongo_id:
                mongo_ids.append(mongo_id)
        return mongo_ids

    async def search_businesses(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[str]:
        """
        Search businesses using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.55)

        Returns:
            List of business IDs (MongoDB ObjectIDs) ordered by relevance
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        # embedding generation may be synchronous (Gemini client used synchronously),
        # keep as-is but allow future async implementations.
        query_embedding = self.embedding_service.generate_embedding(
            query,
            task_type="RETRIEVAL_QUERY"
        )

        # Search in Qdrant with minimum score threshold using query_points (v1.10+)
        threshold = score_threshold if score_threshold is not None else 0.55
        response = await self.qdrant_client.query_points(
            collection_name="businesses",
            query=query_embedding,
            limit=limit,
            score_threshold=threshold
        )

        # query_points returns a QueryResponse object with .points attribute
        results = response.points if hasattr(response, 'points') else response

        print(f"Vector search for '{query}' returned {len(results)} results (threshold: {threshold})")
        for r in results:
            # Handle both old (with metadata wrapper) and new (flat) structures
            mongo_id = r.payload.get('mongo_id') or r.payload.get('metadata', {}).get('mongo_id')
            print(f"  - Score: {r.score}, ID: {mongo_id}")

        # Extract MongoDB IDs from payload (handle both old and new structures)
        mongo_ids = []
        for point in results:
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = point.payload.get("mongo_id") or point.payload.get("metadata", {}).get("mongo_id")
            if mongo_id:
                mongo_ids.append(mongo_id)
        return mongo_ids
