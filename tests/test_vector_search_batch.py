"""Tests for batched embeddings + batched Qdrant search in VectorSearchService.

Everything is mocked: no Gemini calls, no Qdrant, no network. The point is to
pin down (a) that N queries cost ONE embedding call and ONE Qdrant call, (b) that
results stay aligned with the queries that produced them, and (c) that every
fallback path still returns the same answers.
"""

import importlib.util
from types import SimpleNamespace

import pytest

from services.vector_search_service import VectorSearchService, VectorSearchResult

# The chat tests at the bottom import AiRagService, which pulls in the Anthropic
# SDK. Skip just those where it isn't installed instead of losing the whole file.
requires_anthropic = pytest.mark.skipif(
    importlib.util.find_spec("anthropic") is None,
    reason="anthropic SDK not installed; AiRagService cannot be imported",
)


# --------------------------------------------------------------------------- #
# Mocks
# --------------------------------------------------------------------------- #


class MockEmbeddingService:
    """Stands in for GeminiEmbeddingService, recording how it was called."""

    def __init__(self, batch_raises=False, batch_returns_wrong_count=False):
        self.single_calls = []
        self.batch_calls = []
        self.batch_raises = batch_raises
        self.batch_returns_wrong_count = batch_returns_wrong_count

    @staticmethod
    def _vector_for(text):
        """Deterministic fake vector, so a test can tell which text produced it."""
        return [float(len(text)), float(ord(text[0]))]

    def generate_embedding(self, text, task_type=None):
        self.single_calls.append((text, task_type))
        return self._vector_for(text)

    def generate_embeddings_batch(self, texts, task_type=None):
        self.batch_calls.append((list(texts), task_type))
        if self.batch_raises:
            raise RuntimeError("batch endpoint unavailable")
        vectors = [self._vector_for(t) for t in texts]
        if self.batch_returns_wrong_count:
            vectors = vectors[:-1]
        return vectors


def _point(mongo_id, score=0.9, name=None, nested=False):
    """A Qdrant hit. `nested` uses the legacy metadata-wrapper payload shape."""
    if nested:
        payload = {"metadata": {"mongo_id": mongo_id, "name": name}}
    else:
        payload = {"mongo_id": mongo_id, "name": name}
    return SimpleNamespace(payload=payload, score=score)


class MockQdrantClient:
    """Stands in for AsyncQdrantClient.

    `points_by_vector` maps a vector's first component to the hits it returns, so
    a test can assert that each query got its own results back.
    """

    def __init__(self, points_by_vector=None, batch_raises=False, has_batch=True):
        self.points_by_vector = points_by_vector or {}
        self.batch_raises = batch_raises
        self.single_calls = []
        self.batch_calls = []
        if not has_batch:
            # Simulate an older qdrant-client with no batch endpoint.
            self.query_batch_points = None

    def _points(self, vector):
        return self.points_by_vector.get(vector[0], [])

    async def query_points(self, collection_name, query, limit, score_threshold):
        self.single_calls.append((collection_name, query, limit, score_threshold))
        return SimpleNamespace(points=self._points(query))

    async def query_batch_points(self, collection_name, requests):
        self.batch_calls.append((collection_name, requests))
        if self.batch_raises:
            raise RuntimeError("batch query unsupported by this server")
        return [SimpleNamespace(points=self._points(r.query)) for r in requests]


class ServiceUnderTest(VectorSearchService):
    """Real service with both dependencies swapped.

    A subclass rather than a patched instance on purpose: overwriting
    `VectorSearchService.qdrant_client` would leak into every other test that
    imports the class in the same session.
    """

    def __init__(self, embedding=None, qdrant=None):
        self.embedding_service = embedding or MockEmbeddingService()
        self._qdrant = qdrant or MockQdrantClient()

    @property
    def qdrant_client(self):
        return self._qdrant


def build_service(embedding=None, qdrant=None):
    return ServiceUnderTest(embedding, qdrant)


# Fake vectors are keyed by their first component, which is len(text) — so the
# query words below must have distinct lengths.
PIZZA = float(len("pizza"))          # 5
HELADO = float(len("helado"))        # 6
ESPAGUETI = float(len("espagueti"))  # 9


# --------------------------------------------------------------------------- #
# Batching: the actual point of the change
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_multiple_queries_use_one_embedding_call_and_one_qdrant_call():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={
            PIZZA: [_point("p1", name="Pizza de aceituna")],
            HELADO: [_point("h1", name="Helado de fresa")],
            ESPAGUETI: [_point("e1", name="Espagueti")],
        }
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado", "espagueti"])

    assert len(embedding.batch_calls) == 1, "should embed all queries in one request"
    assert embedding.single_calls == [], "should not fall back to per-text embedding"
    assert len(qdrant.batch_calls) == 1, "should hit Qdrant once for all queries"
    assert qdrant.single_calls == []

    assert [[r.mongo_id for r in group] for group in results] == [["p1"], ["h1"], ["e1"]]


@pytest.mark.asyncio
async def test_results_stay_aligned_with_their_query():
    """Result i must belong to query i, even when some queries find nothing."""
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={
            PIZZA: [_point("p1")],
            ESPAGUETI: [_point("e1"), _point("e2")],
            # HELADO deliberately absent -> no hits
        }
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado", "espagueti"])

    assert [[r.mongo_id for r in g] for g in results] == [["p1"], [], ["e1", "e2"]]


@pytest.mark.asyncio
async def test_batch_requests_ask_for_payload():
    """Regression guard: QueryRequest defaults with_payload to None (server: false),
    and the mongo_id lives in the payload. Forgetting it returns zero results."""
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(points_by_vector={PIZZA: [_point("p1")], HELADO: []})
    service = build_service(embedding, qdrant)

    await service.search_products_batch(["pizza", "helado"])

    _, requests = qdrant.batch_calls[0]
    assert all(r.with_payload is True for r in requests)


@pytest.mark.asyncio
async def test_thresholds_and_limits_are_per_collection():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient()
    service = build_service(embedding, qdrant)

    await service.search_products_batch(["pizza", "helado"], limit=7)
    collection, requests = qdrant.batch_calls[0]
    assert collection == "products"
    assert all(r.score_threshold == 0.45 and r.limit == 7 for r in requests)

    await service.search_branches_batch(["pizza", "helado"])
    collection, requests = qdrant.batch_calls[1]
    assert collection == "branches"
    assert all(r.score_threshold == 0.55 for r in requests)

    await service.search_businesses_batch(["pizza", "helado"], score_threshold=0.9)
    collection, requests = qdrant.batch_calls[2]
    assert collection == "businesses"
    assert all(r.score_threshold == 0.9 for r in requests)


# --------------------------------------------------------------------------- #
# Single query: must behave exactly as before (the app's normal search uses it)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_single_query_keeps_the_old_path():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(points_by_vector={PIZZA: [_point("p1", name="Pizza")]})
    service = build_service(embedding, qdrant)

    results = await service.search_products("pizza")

    assert embedding.single_calls == [("pizza", "RETRIEVAL_QUERY")]
    assert embedding.batch_calls == [], "one query must not go through the batch API"
    assert len(qdrant.single_calls) == 1 and qdrant.batch_calls == []
    assert [r.mongo_id for r in results] == ["p1"]
    assert results[0].name == "Pizza"


@pytest.mark.asyncio
async def test_single_query_returns_flat_list_not_nested():
    service = build_service(
        MockEmbeddingService(),
        MockQdrantClient(points_by_vector={PIZZA: [_point("p1")]}),
    )
    results = await service.search_products("pizza")
    assert isinstance(results, list)
    assert all(isinstance(r, VectorSearchResult) for r in results)


# --------------------------------------------------------------------------- #
# Fallbacks — none of them may change the answer
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_falls_back_to_per_text_embedding_when_batch_raises():
    embedding = MockEmbeddingService(batch_raises=True)
    qdrant = MockQdrantClient(
        points_by_vector={PIZZA: [_point("p1")], HELADO: [_point("h1")]}
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado"])

    assert len(embedding.batch_calls) == 1, "it should have tried the batch first"
    assert [t for t, _ in embedding.single_calls] == ["pizza", "helado"]
    assert [[r.mongo_id for r in g] for g in results] == [["p1"], ["h1"]]


@pytest.mark.asyncio
async def test_falls_back_when_batch_returns_too_few_vectors():
    """A short batch would silently pair queries with the wrong vectors."""
    embedding = MockEmbeddingService(batch_returns_wrong_count=True)
    qdrant = MockQdrantClient(
        points_by_vector={PIZZA: [_point("p1")], HELADO: [_point("h1")]}
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado"])

    assert [t for t, _ in embedding.single_calls] == ["pizza", "helado"]
    assert [[r.mongo_id for r in g] for g in results] == [["p1"], ["h1"]]


@pytest.mark.asyncio
async def test_falls_back_to_single_queries_when_qdrant_batch_raises():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={PIZZA: [_point("p1")], HELADO: [_point("h1")]},
        batch_raises=True,
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado"])

    assert len(qdrant.batch_calls) == 1, "it should have tried the batch first"
    assert len(qdrant.single_calls) == 2
    assert [[r.mongo_id for r in g] for g in results] == [["p1"], ["h1"]]


@pytest.mark.asyncio
async def test_works_on_a_client_without_the_batch_endpoint():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={PIZZA: [_point("p1")], HELADO: [_point("h1")]},
        has_batch=False,
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["pizza", "helado"])

    assert len(qdrant.single_calls) == 2
    assert [[r.mongo_id for r in g] for g in results] == [["p1"], ["h1"]]


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_empty_query_list_touches_nothing():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient()
    service = build_service(embedding, qdrant)

    assert await service.search_products_batch([]) == []
    assert embedding.batch_calls == [] and embedding.single_calls == []
    assert qdrant.batch_calls == [] and qdrant.single_calls == []


@pytest.mark.asyncio
async def test_blank_queries_are_skipped_but_keep_their_slot():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(points_by_vector={PIZZA: [_point("p1")]})
    service = build_service(embedding, qdrant)

    results = await service.search_products_batch(["", "pizza", "   "])

    assert [[r.mongo_id for r in g] for g in results] == [[], ["p1"], []]
    # Only the real query was embedded, so it took the single-text path.
    assert [t for t, _ in embedding.single_calls] == ["pizza"]


@pytest.mark.asyncio
async def test_all_blank_queries_touch_nothing():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient()
    service = build_service(embedding, qdrant)

    assert await service.search_products_batch(["", "  "]) == [[], []]
    assert embedding.batch_calls == [] and embedding.single_calls == []
    assert qdrant.batch_calls == [] and qdrant.single_calls == []


@pytest.mark.asyncio
async def test_legacy_nested_payload_still_parsed():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={PIZZA: [_point("p1", name="Pizza", nested=True)]}
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products("pizza")

    assert [r.mongo_id for r in results] == ["p1"]
    assert results[0].name == "Pizza"


@pytest.mark.asyncio
async def test_hits_without_mongo_id_or_payload_are_dropped():
    embedding = MockEmbeddingService()
    qdrant = MockQdrantClient(
        points_by_vector={
            PIZZA: [
                _point("p1"),
                SimpleNamespace(payload=None, score=0.9),        # no payload
                SimpleNamespace(payload={"name": "x"}, score=0.8),  # no mongo_id
            ]
        }
    )
    service = build_service(embedding, qdrant)

    results = await service.search_products("pizza")

    assert [r.mongo_id for r in results] == ["p1"]


@pytest.mark.asyncio
async def test_response_without_points_attribute_is_accepted():
    """Older/raw Qdrant responses come back as a plain list of hits."""
    embedding = MockEmbeddingService()

    class RawListQdrant(MockQdrantClient):
        async def query_points(self, collection_name, query, limit, score_threshold):
            self.single_calls.append((collection_name, query, limit, score_threshold))
            return self._points(query)  # a bare list, not a QueryResponse

    qdrant = RawListQdrant(points_by_vector={PIZZA: [_point("p1")]})
    service = build_service(embedding, qdrant)

    results = await service.search_products("pizza")

    assert [r.mongo_id for r in results] == ["p1"]


# --------------------------------------------------------------------------- #
# The chat's hybrid retrieval, which is what actually consumes the batch
# --------------------------------------------------------------------------- #


class MockVectorSearch:
    """Records how the chat asks for dense results."""

    def __init__(self, by_query=None, raises=False):
        self.by_query = by_query or {}
        self.raises = raises
        self.product_batch_calls = []
        self.branch_batch_calls = []

    def _results(self, queries):
        if self.raises:
            raise RuntimeError("qdrant unreachable")
        return [
            [VectorSearchResult(mongo_id=i, score=0.9) for i in self.by_query.get(q, [])]
            for q in queries
        ]

    async def search_products_batch(self, queries, limit=10):
        self.product_batch_calls.append(list(queries))
        return self._results(queries)

    async def search_branches_batch(self, queries, limit=10):
        self.branch_batch_calls.append(list(queries))
        return self._results(queries)


def build_chat(vector_search, keyword_map=None, keyword_raises=False):
    """AiRagService with retrieval mocked and no __init__ (no API key needed)."""
    from services.ai_rag_service import AiRagService

    class ChatUnderTest(AiRagService):
        def __init__(self):
            self.vector_search = vector_search
            self.keyword_calls = []

        async def _keyword_ids(self, collection, query, limit=20):
            self.keyword_calls.append((collection, query))
            if keyword_raises:
                raise RuntimeError("mongo down")
            return (keyword_map or {}).get(query, [])

    return ChatUnderTest()


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_asks_for_all_dense_queries_in_one_batch():
    vector_search = MockVectorSearch({"pizza": ["p1"], "helado": ["h1"], "espagueti": ["e1"]})
    chat = build_chat(vector_search)

    ids = await chat._hybrid_product_ids(["pizza", "helado", "espagueti"])

    assert vector_search.product_batch_calls == [["pizza", "helado", "espagueti"]], \
        "the three dense legs must travel as a single batched call"
    assert len(chat.keyword_calls) == 3, "keyword legs stay one per query"
    assert set(ids) == {"p1", "h1", "e1"}


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_fuses_dense_and_keyword_rankings():
    vector_search = MockVectorSearch({"pizza": ["shared", "only_vector"]})
    chat = build_chat(vector_search, keyword_map={"pizza": ["shared", "only_keyword"]})

    ids = await chat._hybrid_product_ids(["pizza"])

    assert ids[0] == "shared", "an id ranked by both legs must come first"
    assert set(ids) == {"shared", "only_vector", "only_keyword"}


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_survives_the_dense_leg_failing():
    chat = build_chat(
        MockVectorSearch(raises=True), keyword_map={"pizza": ["k1"]}
    )

    assert await chat._hybrid_product_ids(["pizza"]) == ["k1"]


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_survives_the_keyword_leg_failing():
    chat = build_chat(MockVectorSearch({"pizza": ["v1"]}), keyword_raises=True)

    assert await chat._hybrid_product_ids(["pizza"]) == ["v1"]


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_branch_search_uses_the_branch_batch():
    vector_search = MockVectorSearch({"pizzeria": ["b1"]})
    chat = build_chat(vector_search)

    ids = await chat._hybrid_branch_ids(["pizzeria"])

    assert vector_search.branch_batch_calls == [["pizzeria"]]
    assert vector_search.product_batch_calls == []
    assert ids == ["b1"]


@requires_anthropic
@pytest.mark.asyncio
async def test_chat_with_no_queries_calls_nothing():
    vector_search = MockVectorSearch()
    chat = build_chat(vector_search)

    assert await chat._hybrid_product_ids([]) == []
    assert vector_search.product_batch_calls == []
    assert chat.keyword_calls == []
