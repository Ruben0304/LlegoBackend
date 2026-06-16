"""Qdrant client singleton."""
import asyncio
import logging
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams
from typing import Optional, Dict, Any
from core.config import settings

logger = logging.getLogger(__name__)

qdrant_client: Optional[AsyncQdrantClient] = None

# Max seconds to wait for the startup connection test — must be short so it
# doesn't block Railway's health-check and cause 502s.
_STARTUP_PROBE_TIMEOUT = 5


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
    }
    if settings.qdrant_api_key:
        connection_params["api_key"] = settings.qdrant_api_key

    try:
        client = AsyncQdrantClient(**connection_params)

        # Probe with a hard cap so a dead Qdrant never blocks startup.
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
            f"⚠️ Qdrant probe timed out after {_STARTUP_PROBE_TIMEOUT}s — "
            "vector search disabled until Qdrant is reachable"
        )
        qdrant_client = None
        return False
    except Exception as e:
        logger.warning(
            f"⚠️ Qdrant unavailable ({type(e).__name__}: {e}) — "
            "vector search disabled until Qdrant is reachable"
        )
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
        logger.error("Qdrant client not initialized. Call connect_to_qdrant() first.")
        raise RuntimeError("Qdrant client not initialized. Call connect_to_qdrant() first.")

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
