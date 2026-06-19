"""Qdrant client singleton."""
import asyncio
import logging
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams
from typing import Optional, Dict, Any, List, Tuple
from core.config import settings

logger = logging.getLogger(__name__)

qdrant_client: Optional[AsyncQdrantClient] = None

# Collections expected by the app. Created idempotently on startup.
EXPECTED_COLLECTIONS: Tuple[str, ...] = ("products", "branches", "businesses", "users")

# Payload indexes per collection: (field_name, schema). Required for fast
# server-side filtering (by branchId, category, availability, geo, ...) and for
# the mongo_id lookups the repositories do on every write.
PAYLOAD_INDEXES: Dict[str, Tuple[Tuple[str, PayloadSchemaType], ...]] = {
    "products": (
        ("mongo_id", PayloadSchemaType.KEYWORD),
        ("branchId", PayloadSchemaType.KEYWORD),
        ("categoryId", PayloadSchemaType.KEYWORD),
        ("availability", PayloadSchemaType.BOOL),
    ),
    "branches": (
        ("mongo_id", PayloadSchemaType.KEYWORD),
        ("businessId", PayloadSchemaType.KEYWORD),
        ("tipos", PayloadSchemaType.KEYWORD),
        ("isActive", PayloadSchemaType.BOOL),
        ("location", PayloadSchemaType.GEO),
    ),
    "businesses": (
        ("mongo_id", PayloadSchemaType.KEYWORD),
        ("approvalStatus", PayloadSchemaType.KEYWORD),
        ("isActive", PayloadSchemaType.BOOL),
    ),
}

# Max seconds to wait for the startup connection test.
# Railway cold starts can take 10-15s, so we give enough margin without
# blocking the health-check indefinitely.
_STARTUP_PROBE_TIMEOUT = 20


_MAX_RETRIES = 3
_RETRY_DELAY = 5  # seconds between attempts


async def connect_to_qdrant():
    """Connect to Qdrant (optional — won't fail startup if unavailable)."""
    global qdrant_client

    host = settings.qdrant_host
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    host = host.rstrip("/")

    protocol = "https" if settings.qdrant_https else "http"
    logger.info(
        f"🔌 Connecting to Qdrant at {protocol}://{host}:{settings.qdrant_port} "
        f"(api_key={'yes' if settings.qdrant_api_key else 'no'})"
    )

    connection_params: Dict[str, Any] = {
        "host": host,
        "port": settings.qdrant_port,
        "grpc_port": settings.qdrant_grpc_port,
        "prefer_grpc": settings.qdrant_prefer_grpc,
        "https": settings.qdrant_https,
        "timeout": settings.qdrant_timeout,
        "check_compatibility": False,
    }
    if settings.qdrant_api_key:
        connection_params["api_key"] = settings.qdrant_api_key

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            client = AsyncQdrantClient(**connection_params)

            collections = await asyncio.wait_for(
                client.get_collections(),
                timeout=_STARTUP_PROBE_TIMEOUT,
            )
            names = [c.name for c in collections.collections]
            logger.info(f"✅ Qdrant connected — collections: {names or '(none)'}")
            qdrant_client = client
            return True

        except asyncio.TimeoutError:
            logger.warning(
                f"⚠️ Qdrant probe timed out after {_STARTUP_PROBE_TIMEOUT}s "
                f"(attempt {attempt}/{_MAX_RETRIES})"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Qdrant unavailable ({type(e).__name__}: {e}) "
                f"(attempt {attempt}/{_MAX_RETRIES})"
            )

        if attempt < _MAX_RETRIES:
            logger.info(f"Retrying Qdrant connection in {_RETRY_DELAY}s...")
            await asyncio.sleep(_RETRY_DELAY)

    logger.warning("⚠️ Qdrant unreachable after all retries — vector search disabled")
    qdrant_client = None
    return False


async def close_qdrant_connection():
    """Close Qdrant connection"""
    global qdrant_client
    if qdrant_client:
        try:
            await qdrant_client.close()
            logger.info("✓ Qdrant connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing Qdrant connection: {str(e)}", exc_info=True)
        finally:
            qdrant_client = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Get Qdrant client instance"""
    if qdrant_client is None:
        raise RuntimeError(
            "Qdrant client not initialized — startup probe failed. "
            "Check QDRANT_HOST/PORT/HTTPS env vars and Qdrant service health."
        )

    return qdrant_client


async def create_collection(
    collection_name: str,
    vector_size: int = 768,
    distance: Distance = Distance.COSINE,
    **collection_params: Dict[str, Any]
) -> bool:
    """
    Create a new collection in Qdrant.

    Args:
        collection_name: Name of the collection
        vector_size: Dimension of vectors (default: 768)
        distance: Distance metric (default: Distance.COSINE)
        **collection_params: Additional collection parameters

    Returns:
        bool: True if collection was created successfully, False otherwise
    """
    logger.info(f"Creating collection '{collection_name}' with vector size {vector_size} and distance {distance}")

    try:
        client = get_qdrant_client()

        # Verificar si la colección ya existe
        collections = await client.get_collections()
        existing_collections = [c.name for c in collections.collections]

        if collection_name in existing_collections:
            logger.warning(f"Collection '{collection_name}' already exists")
            return True

        # Crear la colección con parámetros adicionales si se proporcionan
        create_params = {
            "collection_name": collection_name,
            "vectors_config": VectorParams(
                size=vector_size,
                distance=distance
            ),
            **collection_params
        }

        logger.debug(f"Collection creation parameters: {create_params}")

        # Crear la colección
        result = await client.create_collection(**create_params)

        if result:
            logger.info(f"✓ Successfully created collection: {collection_name} "
                       f"(size={vector_size}, distance={distance.value})")
            return True
        else:
            logger.error(f"Failed to create collection: {collection_name}")
            return False

    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"✗ Error creating collection '{collection_name}': {error_type} - {str(e)}")
        logger.debug(f"Full error details:", exc_info=True)

        # Manejo específico de errores comunes
        if "already exists" in str(e).lower():
            logger.warning(f"Collection '{collection_name}' already exists")
            return True
        elif "invalid vector size" in str(e).lower():
            logger.error(f"Invalid vector size: {vector_size}. Check Qdrant version compatibility.")

        # Relanzar la excepción para manejo externo
        raise


async def delete_by_mongo_id(collection_name: str, mongo_id: str) -> bool:
    """Delete every point whose payload.mongo_id matches.

    Uses a filter selector so it removes ALL matching points in one call —
    robust to duplicates and to legacy points stored under either a raw
    ObjectId or a uuid5 id. Requires the mongo_id payload index for speed.
    Never raises (MongoDB stays the source of truth).
    """
    try:
        client = get_qdrant_client()
    except RuntimeError:
        return False
    try:
        await client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="mongo_id",
                            match=models.MatchValue(value=str(mongo_id)),
                        )
                    ]
                )
            ),
        )
        return True
    except Exception as e:
        logger.error(
            f"Error deleting {collection_name} mongo_id={mongo_id} from Qdrant: "
            f"{type(e).__name__}: {e}"
        )
        return False


async def ensure_payload_indexes(collection_name: str) -> None:
    """Create the configured payload indexes for a collection (idempotent)."""
    indexes = PAYLOAD_INDEXES.get(collection_name)
    if not indexes:
        return

    client = get_qdrant_client()
    for field_name, schema in indexes:
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema,
            )
        except Exception as e:
            # Already-exists is expected and harmless; log anything else.
            msg = str(e).lower()
            if "already exists" not in msg and "already" not in msg:
                logger.warning(
                    f"Could not create payload index {collection_name}.{field_name}: "
                    f"{type(e).__name__}: {e}"
                )


async def ensure_collections_and_indexes() -> None:
    """Create expected collections + payload indexes if missing (idempotent).

    Safe to call on every startup: existing collections are left untouched and
    re-creating an existing payload index is a no-op. Never raises — vector
    features degrade gracefully if Qdrant is unavailable.
    """
    try:
        client = get_qdrant_client()
    except RuntimeError:
        logger.warning("Qdrant unavailable — skipping collection/index bootstrap")
        return

    try:
        existing = {c.name for c in (await client.get_collections()).collections}
    except Exception as e:
        logger.warning(f"Could not list Qdrant collections: {type(e).__name__}: {e}")
        return

    for collection_name in EXPECTED_COLLECTIONS:
        try:
            if collection_name not in existing:
                await create_collection(
                    collection_name=collection_name,
                    vector_size=settings.embedding_dimension,
                    distance=Distance.COSINE,
                )
            await ensure_payload_indexes(collection_name)
        except Exception as e:
            logger.warning(
                f"Could not bootstrap collection '{collection_name}': "
                f"{type(e).__name__}: {e}"
            )
