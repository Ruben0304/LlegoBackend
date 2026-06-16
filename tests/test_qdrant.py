"""
Integration tests for Qdrant — connectivity, insert/read/delete, performance, and consistency.

Runs against the Railway Qdrant instance (reads .env from project root).

Usage:
    python3 -m pytest tests/test_qdrant.py -v -s
    python3 -m pytest tests/test_qdrant.py::TestProductCreation -v -s   # solo creación

Sections:
  TestConnectivity      — ping, collections exist, not empty
  TestInsertReadDelete  — upsert a synthetic point, read it back, delete it
  TestSearchPerformance — timing benchmarks for normal and extreme cases
  TestDataConsistency   — count parity and full ID cross-check vs MongoDB
  TestProductCreation   — crea un producto real vía ProductRepository y verifica MongoDB + Qdrant
"""

import asyncio
import os
import time
import uuid
from typing import List

import pytest
import pytest_asyncio
from bson import ObjectId
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

load_dotenv()

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

# ── Constants ────────────────────────────────────────────────────────────────

QDRANT_HOST = "qdrant-production-37a8.up.railway.app"
QDRANT_PORT = 443
QDRANT_HTTPS = True
VECTOR_SIZE = 768
EXPECTED_COLLECTIONS = {"products", "branches", "businesses"}
_UUID_NAMESPACE = uuid.UUID("b1e7a000-0000-0000-0000-000000000000")

# Timing thresholds
SEARCH_NORMAL_MAX_S = 2.0   # single search, limit=20
SEARCH_EXTREME_MAX_S = 5.0  # high limit / parallel / full scroll

# Synthetic test point — fake mongo_id that won't collide with real data
_TEST_MONGO_ID = "000000000000000000000001"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        https=QDRANT_HTTPS,
        check_compatibility=False,
    )


def _random_vector(size: int = VECTOR_SIZE) -> List[float]:
    """Unit-norm random vector — avoids importing numpy."""
    import random
    v = [random.gauss(0, 1) for _ in range(size)]
    norm = sum(x ** 2 for x in v) ** 0.5
    return [x / norm for x in v]


def _mongo_id_to_uuid(mongo_id: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, mongo_id))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def qdrant():
    c = _make_client()
    yield c
    await c.close()


@pytest_asyncio.fixture
async def mongo_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo = AsyncIOMotorClient(os.environ["MONGODB_URL"])
    yield mongo["llego"]
    mongo.close()


# ── 1. Connectivity ───────────────────────────────────────────────────────────

class TestConnectivity:
    @pytest.mark.asyncio
    async def test_ping(self, qdrant):
        result = await qdrant.get_collections()
        assert result is not None

    @pytest.mark.asyncio
    async def test_expected_collections_exist(self, qdrant):
        result = await qdrant.get_collections()
        names = {c.name for c in result.collections}
        missing = EXPECTED_COLLECTIONS - names
        assert not missing, f"Colecciones faltantes: {missing}"

    @pytest.mark.asyncio
    async def test_collections_are_not_empty(self, qdrant):
        for name in EXPECTED_COLLECTIONS:
            info = await qdrant.get_collection(name)
            assert info.points_count > 0, f"Colección '{name}' está vacía"
            print(f"\n  {name}: {info.points_count} puntos")


# ── 2. Insert / Read / Delete ─────────────────────────────────────────────────

class TestInsertReadDelete:
    @pytest.mark.asyncio
    async def test_insert_point(self, qdrant):
        point_id = _mongo_id_to_uuid(_TEST_MONGO_ID)
        result = await qdrant.upsert(
            collection_name="products",
            points=[PointStruct(
                id=point_id,
                vector=_random_vector(),
                payload={"mongo_id": _TEST_MONGO_ID, "name": "TEST_POINT_DO_NOT_USE", "_test": True},
            )],
        )
        assert result.status.value == "completed"

    @pytest.mark.asyncio
    async def test_read_point_back(self, qdrant):
        point_id = _mongo_id_to_uuid(_TEST_MONGO_ID)
        results = await qdrant.retrieve(
            collection_name="products",
            ids=[point_id],
            with_payload=True,
        )
        assert len(results) == 1
        payload = results[0].payload
        assert payload["mongo_id"] == _TEST_MONGO_ID
        assert payload["_test"] is True

    @pytest.mark.asyncio
    async def test_delete_point(self, qdrant):
        point_id = _mongo_id_to_uuid(_TEST_MONGO_ID)
        await qdrant.delete(
            collection_name="products",
            points_selector=[point_id],
        )
        results = await qdrant.retrieve(
            collection_name="products",
            ids=[point_id],
            with_payload=False,
        )
        assert len(results) == 0, "El punto de test no fue eliminado"


# ── 3. Search Performance ─────────────────────────────────────────────────────

class TestSearchPerformance:
    @pytest.mark.asyncio
    async def test_search_returns_list(self, qdrant):
        """La búsqueda vectorial devuelve una lista (puede ser vacía si no hay datos)."""
        resp = await qdrant.query_points(
            collection_name="products",
            query=_random_vector(),
            limit=10,
        )
        assert isinstance(resp.points, list)

    @pytest.mark.asyncio
    async def test_search_normal_timing(self, qdrant):
        """Búsqueda normal (limit=20, threshold=0.5) bajo umbral de 2s."""
        start = time.perf_counter()
        await qdrant.query_points(
            collection_name="products",
            query=_random_vector(),
            limit=20,
            score_threshold=0.5,
        )
        elapsed = time.perf_counter() - start
        print(f"\n  Búsqueda normal (limit=20, threshold=0.5): {elapsed * 1000:.1f}ms")
        assert elapsed < SEARCH_NORMAL_MAX_S, f"Tardó {elapsed:.2f}s, máximo {SEARCH_NORMAL_MAX_S}s"

    @pytest.mark.asyncio
    async def test_search_no_threshold_timing(self, qdrant):
        """Búsqueda sin threshold — devuelve los N más cercanos sin filtrar."""
        start = time.perf_counter()
        resp = await qdrant.query_points(
            collection_name="products",
            query=_random_vector(),
            limit=50,
        )
        elapsed = time.perf_counter() - start
        print(f"\n  Sin threshold (limit=50): {elapsed * 1000:.1f}ms, resultados={len(resp.points)}")
        assert elapsed < SEARCH_NORMAL_MAX_S

    @pytest.mark.asyncio
    async def test_search_high_limit_timing(self, qdrant):
        """Caso extremo: limit=500 sin threshold."""
        start = time.perf_counter()
        resp = await qdrant.query_points(
            collection_name="products",
            query=_random_vector(),
            limit=500,
        )
        elapsed = time.perf_counter() - start
        print(f"\n  High-limit (limit=500): {elapsed * 1000:.1f}ms, resultados={len(resp.points)}")
        assert elapsed < SEARCH_EXTREME_MAX_S

    @pytest.mark.asyncio
    async def test_search_10_consecutive_requests(self, qdrant):
        """10 búsquedas seguidas — mide latencia mínima, máxima y promedio."""
        times = []
        for _ in range(10):
            start = time.perf_counter()
            await qdrant.query_points(
                collection_name="products",
                query=_random_vector(),
                limit=20,
            )
            times.append((time.perf_counter() - start) * 1000)

        print(
            f"\n  10 búsquedas consecutivas — "
            f"min={min(times):.1f}ms  max={max(times):.1f}ms  "
            f"avg={sum(times)/len(times):.1f}ms"
        )
        slow = [f"{t:.1f}ms" for t in times if t > SEARCH_NORMAL_MAX_S * 1000]
        assert not slow, f"Requests lentos: {slow}"

    @pytest.mark.asyncio
    async def test_parallel_search_all_collections(self, qdrant):
        """Búsqueda simultánea en las 3 colecciones — simula carga real."""
        vector = _random_vector()
        start = time.perf_counter()
        results = await asyncio.gather(
            qdrant.query_points("products",   query=vector, limit=20),
            qdrant.query_points("branches",   query=vector, limit=20),
            qdrant.query_points("businesses", query=vector, limit=20),
        )
        elapsed = time.perf_counter() - start
        counts = [len(r.points) for r in results]
        print(f"\n  Búsqueda paralela 3 colecciones: {elapsed * 1000:.1f}ms  resultados={counts}")
        assert elapsed < SEARCH_EXTREME_MAX_S


# ── 4. Data Consistency ───────────────────────────────────────────────────────

class TestDataConsistency:
    @pytest.mark.asyncio
    async def test_products_count_matches_mongo(self, qdrant, mongo_db):
        """El número de puntos en Qdrant coincide con documentos en MongoDB."""
        qdrant_info = await qdrant.get_collection("products")
        qdrant_count = qdrant_info.points_count
        mongo_count = await mongo_db["products"].count_documents({})

        print(f"\n  MongoDB: {mongo_count} productos | Qdrant: {qdrant_count} puntos")
        assert qdrant_count == mongo_count, (
            f"Desajuste — MongoDB: {mongo_count}, Qdrant: {qdrant_count}"
        )

    @pytest.mark.asyncio
    async def test_all_qdrant_ids_exist_in_mongo(self, qdrant, mongo_db):
        """Cada mongo_id en Qdrant apunta a un documento real en MongoDB."""
        # Scroll paginado para leer todos los puntos
        all_mongo_ids: List[str] = []
        offset = None
        while True:
            batch, next_offset = await qdrant.scroll(
                collection_name="products",
                with_payload=["mongo_id"],
                limit=500,
                offset=offset,
            )
            for point in batch:
                mid = (point.payload or {}).get("mongo_id")
                if mid:
                    all_mongo_ids.append(mid)
            if next_offset is None:
                break
            offset = next_offset

        print(f"\n  Puntos Qdrant escaneados: {len(all_mongo_ids)}")

        # Verificación masiva en MongoDB por lotes de 500
        missing: List[str] = []
        for i in range(0, len(all_mongo_ids), 500):
            chunk = all_mongo_ids[i : i + 500]
            oids = [ObjectId(mid) for mid in chunk if len(mid) == 24]
            found = await mongo_db["products"].distinct("_id", {"_id": {"$in": oids}})
            found_set = {str(f) for f in found}
            missing += [mid for mid in chunk if mid not in found_set]

        if missing:
            print(f"  ❌ {len(missing)} IDs de Qdrant no encontrados en MongoDB: {missing[:10]}")
        assert not missing, (
            f"{len(missing)} mongo_ids de Qdrant no existen en MongoDB (primeros 10: {missing[:10]})"
        )

    @pytest.mark.asyncio
    async def test_all_mongo_ids_exist_in_qdrant(self, qdrant, mongo_db):
        """Cada producto de MongoDB tiene su punto correspondiente en Qdrant."""
        cursor = mongo_db["products"].find({}, {"_id": 1})
        mongo_ids = [str(doc["_id"]) async for doc in cursor]
        print(f"\n  Productos MongoDB: {len(mongo_ids)}")

        missing_in_qdrant: List[str] = []
        for i in range(0, len(mongo_ids), 100):
            chunk_ids = mongo_ids[i : i + 100]
            chunk_uuids = [_mongo_id_to_uuid(mid) for mid in chunk_ids]
            found = await qdrant.retrieve(
                collection_name="products",
                ids=chunk_uuids,
                with_payload=False,
            )
            found_set = {str(p.id) for p in found}
            for j, uid in enumerate(chunk_uuids):
                if uid not in found_set:
                    missing_in_qdrant.append(chunk_ids[j])

        if missing_in_qdrant:
            print(f"  ❌ {len(missing_in_qdrant)} productos de MongoDB sin punto en Qdrant: {missing_in_qdrant[:10]}")
        assert not missing_in_qdrant, (
            f"{len(missing_in_qdrant)} productos de MongoDB no están en Qdrant "
            f"(primeros 10: {missing_in_qdrant[:10]})"
        )


# ── 5. Product Creation (real repository flow) ────────────────────────────────

class TestProductCreation:
    """
    Prueba el flujo completo de creación de producto usando ProductRepository.create().

    Esto verifica si el problema de los 56 productos sin indexar es un bug activo
    o si simplemente ocurrió cuando Qdrant estaba caído.

    Estrategia:
      1. Inicializar los singletons de MongoDB y Qdrant (igual que en producción)
      2. Crear un producto de prueba con un branchId real de la BD
      3. Verificar que existe en MongoDB
      4. Verificar que existe en Qdrant con el payload correcto
      5. Limpiar (delete de ambos) en el teardown
    """

    @pytest.mark.asyncio
    async def test_create_product_appears_in_mongo_and_qdrant(self):
        from bson import ObjectId
        from datetime import datetime, timezone

        # ── Inicializar singletons (igual que lifespan en producción) ──────────
        from clients.mongodb_client import connect_to_mongo
        from clients.qdrant_client import connect_to_qdrant, get_qdrant_client
        from clients.mongodb_client import get_database

        from clients.gemini_client import connect_to_gemini

        await connect_to_mongo()
        qdrant_ok = await connect_to_qdrant()
        connect_to_gemini()

        # connect_to_mongo() no retorna valor — si falla lanza excepción
        assert qdrant_ok, "No se pudo conectar a Qdrant — verifica QDRANT_HOST en .env"

        db = get_database()
        qclient = get_qdrant_client()

        # ── Obtener un branchId real de la BD ─────────────────────────────────
        branch_doc = await db["branches"].find_one({}, {"_id": 1})
        assert branch_doc, "No hay branches en MongoDB para usar como referencia"
        real_branch_id = str(branch_doc["_id"])
        print(f"\n  Usando branchId real: {real_branch_id}")

        # ── Construir producto de prueba ──────────────────────────────────────
        from domain.models import Product

        product_id = str(ObjectId())
        product = Product(**{
            "_id": product_id,
            "branchId": real_branch_id,
            "name": "PRODUCTO_TEST_CREACION_NO_USAR",
            "description": "Producto sintético creado por test de integración",
            "weight": "0kg",
            "price": 0.01,
            "currency": "USD",
            "image": "https://example.com/test.jpg",
            "availability": False,
            "createdAt": datetime.now(timezone.utc),
        })

        from repositories.product_repository import ProductRepository
        repo = ProductRepository()

        # ── Crear el producto ─────────────────────────────────────────────────
        try:
            import time
            start = time.perf_counter()
            created = await repo.create(product)
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"  ProductRepository.create() tardó: {elapsed_ms:.1f}ms")

            assert created is not None
            assert str(created.id) == product_id

            # ── Verificar en MongoDB ──────────────────────────────────────────
            mongo_doc = await db["products"].find_one({"_id": ObjectId(product_id)})
            assert mongo_doc is not None, f"Producto {product_id} NO encontrado en MongoDB"
            assert mongo_doc["name"] == "PRODUCTO_TEST_CREACION_NO_USAR"
            print(f"  ✅ MongoDB: producto encontrado (name='{mongo_doc['name']}')")

            # ── Verificar en Qdrant ───────────────────────────────────────────
            point_uuid = _mongo_id_to_uuid(product_id)
            qdrant_points = await qclient.retrieve(
                collection_name="products",
                ids=[point_uuid],
                with_payload=True,
            )

            assert len(qdrant_points) == 1, (
                f"Producto {product_id} NO encontrado en Qdrant — "
                "la sincronización falló silenciosamente durante create()"
            )

            payload = qdrant_points[0].payload
            assert payload["mongo_id"] == product_id
            assert payload["name"] == "PRODUCTO_TEST_CREACION_NO_USAR"
            print(f"  ✅ Qdrant: punto encontrado (payload mongo_id='{payload['mongo_id']}')")

        finally:
            # ── Limpieza garantizada aunque el test falle ─────────────────────
            try:
                await db["products"].delete_one({"_id": ObjectId(product_id)})
                point_uuid = _mongo_id_to_uuid(product_id)
                await qclient.delete(
                    collection_name="products",
                    points_selector=[point_uuid],
                )
                print(f"  🧹 Limpieza completada para producto {product_id}")
            except Exception as cleanup_err:
                print(f"  ⚠️ Error en limpieza: {cleanup_err}")
