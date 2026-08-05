"""Vector search service using Qdrant."""
import asyncio
from typing import Any, Dict, List, Optional, Sequence
from dataclasses import dataclass

from clients import get_qdrant_client
from services.embeddings.gemini_service import GeminiEmbeddingService

_QUERY_TASK_TYPE = "RETRIEVAL_QUERY"

# Minimum similarity per collection — the values each search already used.
_DEFAULT_THRESHOLDS = {"products": 0.45, "branches": 0.55, "businesses": 0.55}


@dataclass
class VectorSearchResult:
    """Result from vector search with metadata."""
    mongo_id: str
    score: float
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VectorSearchService:
    """Service for performing vector similarity searches in Qdrant.

    The `*_batch` methods take several queries and resolve them with ONE
    embedding call and ONE Qdrant call, instead of one of each per query. The
    single-query methods are thin wrappers over them, so their behaviour is
    unchanged.
    """

    def __init__(self):
        """Initialize vector search service."""
        self.embedding_service = GeminiEmbeddingService()

    @property
    def qdrant_client(self):
        return get_qdrant_client()

    # ------------------------------------------------------------------ #
    # Single query
    # ------------------------------------------------------------------ #

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """Search products using vector similarity."""
        return await self._search_one("products", query, limit, score_threshold)

    async def search_branches(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """Search branches using vector similarity."""
        return await self._search_one("branches", query, limit, score_threshold)

    async def search_businesses(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[VectorSearchResult]:
        """Search businesses using vector similarity."""
        return await self._search_one("businesses", query, limit, score_threshold)

    # ------------------------------------------------------------------ #
    # Batched queries — one embedding call + one Qdrant call for all of them
    # ------------------------------------------------------------------ #

    async def search_products_batch(
        self,
        queries: Sequence[str],
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[List[VectorSearchResult]]:
        """Search products for several queries at once.

        Returns one result list per query, aligned with `queries` by index.
        """
        return await self._search_many("products", queries, limit, score_threshold)

    async def search_branches_batch(
        self,
        queries: Sequence[str],
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[List[VectorSearchResult]]:
        """Search branches for several queries at once."""
        return await self._search_many("branches", queries, limit, score_threshold)

    async def search_businesses_batch(
        self,
        queries: Sequence[str],
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[List[VectorSearchResult]]:
        """Search businesses for several queries at once."""
        return await self._search_many("businesses", queries, limit, score_threshold)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _search_one(
        self,
        collection: str,
        query: str,
        limit: int,
        score_threshold: Optional[float],
    ) -> List[VectorSearchResult]:
        results = await self._search_many(collection, [query], limit, score_threshold)
        return results[0] if results else []

    async def _search_many(
        self,
        collection: str,
        queries: Sequence[str],
        limit: int,
        score_threshold: Optional[float],
    ) -> List[List[VectorSearchResult]]:
        # Blank queries are never embedded, but they still occupy their slot so
        # callers can zip the output against their input.
        out: List[List[VectorSearchResult]] = [[] for _ in queries]
        live = [(i, q) for i, q in enumerate(queries) if q and q.strip()]
        if not live:
            return out

        threshold = (
            score_threshold
            if score_threshold is not None
            else _DEFAULT_THRESHOLDS.get(collection, 0.55)
        )

        vectors = await self._embed([q for _, q in live])
        responses = await self._query(collection, vectors, limit, threshold)

        for (index, query), response in zip(live, responses):
            out[index] = self._parse_response(response, query, threshold)
        return out

    async def _embed(self, texts: List[str]) -> List[List[float]]:
        """Vectorize `texts`, preferring a single batched call.

        Falls back to one call per text if the batch endpoint fails or answers
        with a different number of vectors than we asked for — a mismatch would
        silently pair queries with the wrong vectors.
        """
        if len(texts) == 1:
            vector = await asyncio.to_thread(
                self.embedding_service.generate_embedding, texts[0], _QUERY_TASK_TYPE
            )
            return [vector]

        try:
            vectors = await asyncio.to_thread(
                self.embedding_service.generate_embeddings_batch,
                texts,
                _QUERY_TASK_TYPE,
            )
            if len(vectors) == len(texts):
                return list(vectors)
            print(
                f"[vector search] batch embedding returned {len(vectors)} vectors for "
                f"{len(texts)} texts; falling back to one call per text"
            )
        except Exception as exc:
            print(f"[vector search] batch embedding failed ({exc}); one call per text")

        return list(
            await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self.embedding_service.generate_embedding, text, _QUERY_TASK_TYPE
                    )
                    for text in texts
                )
            )
        )

    async def _query(
        self,
        collection: str,
        vectors: List[List[float]],
        limit: int,
        threshold: float,
    ) -> List[Any]:
        """Run one Qdrant search per vector, batched into a single call if possible."""
        if len(vectors) > 1:
            try:
                from qdrant_client import models as qmodels

                requests = [
                    qmodels.QueryRequest(
                        query=vector,
                        limit=limit,
                        score_threshold=threshold,
                        # Required: unlike query_points, the batch API defaults to
                        # NOT returning the payload, and the payload is where the
                        # mongo_id lives — without this every hit is discarded.
                        with_payload=True,
                    )
                    for vector in vectors
                ]
                return list(
                    await self.qdrant_client.query_batch_points(
                        collection_name=collection, requests=requests
                    )
                )
            except Exception as exc:
                print(f"[vector search] batch query failed ({exc}); one query per vector")

        return list(
            await asyncio.gather(
                *(
                    self.qdrant_client.query_points(
                        collection_name=collection,
                        query=vector,
                        limit=limit,
                        score_threshold=threshold,
                    )
                    for vector in vectors
                )
            )
        )

    @staticmethod
    def _parse_response(
        response: Any, query: str, threshold: float
    ) -> List[VectorSearchResult]:
        """Pull mongo ids and metadata out of a Qdrant response."""
        # query_points returns a QueryResponse object with .points attribute
        results = response.points if hasattr(response, "points") else response

        count = len(results) if hasattr(results, "__len__") else 0
        print(
            f"Vector search for '{query}' returned {count} results (threshold: {threshold})"
        )

        search_results: List[VectorSearchResult] = []
        for point in results:
            if not point or not hasattr(point, "payload") or point.payload is None:
                continue

            payload = point.payload
            # Try flat structure first, then old metadata wrapper structure
            mongo_id = (
                payload.get("mongo_id")
                if isinstance(payload.get("mongo_id"), str)
                else None
            )
            if not mongo_id and isinstance(payload.get("metadata"), dict):
                mongo_id = payload.get("metadata", {}).get("mongo_id")

            name = payload.get("name") if isinstance(payload.get("name"), str) else None
            if not name and isinstance(payload.get("metadata"), dict):
                name = payload.get("metadata", {}).get("name")

            if mongo_id and isinstance(mongo_id, str):
                score = point.score if hasattr(point, "score") else 0.0
                print(f"  - Score: {score}, ID: {mongo_id}, Name: {name}")
                search_results.append(
                    VectorSearchResult(
                        mongo_id=mongo_id,
                        score=score,
                        name=name,
                        metadata=dict(payload) if payload else None,
                    )
                )
        return search_results
