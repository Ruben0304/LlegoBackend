"""Vector search service using Qdrant."""
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from clients import get_qdrant_client
from services.embeddings.gemini_service import GeminiEmbeddingService


@dataclass
class VectorSearchResult:
    """Result from vector search with metadata."""
    mongo_id: str
    score: float
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VectorSearchService:
    """Service for performing vector similarity searches in Qdrant."""

    def __init__(self):
        """Initialize vector search service."""
        self.embedding_service = GeminiEmbeddingService()

    @property
    def qdrant_client(self):
        return get_qdrant_client()

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """
        Search products using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.60)

        Returns:
            List of VectorSearchResult with mongo_id, score, name, and metadata
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        query_embedding = await asyncio.to_thread(
            self.embedding_service.generate_embedding,
            query,
            "RETRIEVAL_QUERY",
        )

        # Search in Qdrant with minimum score threshold using query_points (v1.10+)
        threshold = score_threshold if score_threshold is not None else 0.45
        response = await self.qdrant_client.query_points(
            collection_name="products",
            query=query_embedding,
            limit=limit,
            score_threshold=threshold
        )

        # query_points returns a QueryResponse object with .points attribute
        results = response.points if hasattr(response, 'points') else response

        count = len(results) if hasattr(results, '__len__') else 0
        print(f"Vector search for '{query}' returned {count} results (threshold: {threshold})")

        # Extract MongoDB IDs and metadata from payload
        search_results: List[VectorSearchResult] = []
        for point in results:
            if not point or not hasattr(point, 'payload') or point.payload is None:
                continue

            payload = point.payload
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = payload.get("mongo_id") if isinstance(payload.get("mongo_id"), str) else None
            if not mongo_id and isinstance(payload.get("metadata"), dict):
                mongo_id = payload.get("metadata", {}).get("mongo_id")

            name = payload.get("name") if isinstance(payload.get("name"), str) else None
            if not name and isinstance(payload.get("metadata"), dict):
                name = payload.get("metadata", {}).get("name")

            if mongo_id and isinstance(mongo_id, str):
                score = point.score if hasattr(point, 'score') else 0.0
                print(f"  - Score: {score}, ID: {mongo_id}, Name: {name}")
                search_results.append(VectorSearchResult(
                    mongo_id=mongo_id,
                    score=score,
                    name=name,
                    metadata=dict(payload) if payload else None
                ))
        return search_results

    async def search_branches(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """
        Search branches using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.55)

        Returns:
            List of VectorSearchResult with mongo_id, score, name, and metadata
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        query_embedding = await asyncio.to_thread(
            self.embedding_service.generate_embedding,
            query,
            "RETRIEVAL_QUERY",
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

        count = len(results) if hasattr(results, '__len__') else 0
        print(f"Vector search for '{query}' returned {count} results (threshold: {threshold})")

        # Extract MongoDB IDs and metadata from payload
        search_results: List[VectorSearchResult] = []
        for point in results:
            if not point or not hasattr(point, 'payload') or point.payload is None:
                continue

            payload = point.payload
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = payload.get("mongo_id") if isinstance(payload.get("mongo_id"), str) else None
            if not mongo_id and isinstance(payload.get("metadata"), dict):
                mongo_id = payload.get("metadata", {}).get("mongo_id")

            name = payload.get("name") if isinstance(payload.get("name"), str) else None
            if not name and isinstance(payload.get("metadata"), dict):
                name = payload.get("metadata", {}).get("name")

            if mongo_id and isinstance(mongo_id, str):
                score = point.score if hasattr(point, 'score') else 0.0
                print(f"  - Score: {score}, ID: {mongo_id}, Name: {name}")
                search_results.append(VectorSearchResult(
                    mongo_id=mongo_id,
                    score=score,
                    name=name,
                    metadata=dict(payload) if payload else None
                ))
        return search_results

    async def search_businesses(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """
        Search businesses using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score (optional, default: 0.55)

        Returns:
            List of VectorSearchResult with mongo_id, score, name, and metadata
        """
        # Generate query embedding with RETRIEVAL_QUERY task type
        query_embedding = await asyncio.to_thread(
            self.embedding_service.generate_embedding,
            query,
            "RETRIEVAL_QUERY",
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

        count = len(results) if hasattr(results, '__len__') else 0
        print(f"Vector search for '{query}' returned {count} results (threshold: {threshold})")

        # Extract MongoDB IDs and metadata from payload
        search_results: List[VectorSearchResult] = []
        for point in results:
            if not point or not hasattr(point, 'payload') or point.payload is None:
                continue

            payload = point.payload
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = payload.get("mongo_id") if isinstance(payload.get("mongo_id"), str) else None
            if not mongo_id and isinstance(payload.get("metadata"), dict):
                mongo_id = payload.get("metadata", {}).get("mongo_id")

            name = payload.get("name") if isinstance(payload.get("name"), str) else None
            if not name and isinstance(payload.get("metadata"), dict):
                name = payload.get("metadata", {}).get("name")

            if mongo_id and isinstance(mongo_id, str):
                score = point.score if hasattr(point, 'score') else 0.0
                print(f"  - Score: {score}, ID: {mongo_id}, Name: {name}")
                search_results.append(VectorSearchResult(
                    mongo_id=mongo_id,
                    score=score,
                    name=name,
                    metadata=dict(payload) if payload else None
                ))
        return search_results
