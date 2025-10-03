"""Qdrant client singleton."""
import sys
import logging
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams
from typing import Optional, Dict, Any
from core.config import settings

# Configurar logger
logger = logging.getLogger(__name__)

# Global Qdrant client instance
qdrant_client: Optional[AsyncQdrantClient] = None


async def connect_to_qdrant():
    """Connect to Qdrant (optional - won't fail startup if unavailable)"""
    global qdrant_client

    # Log de variables de entorno para debug
    import os
    logger.info("🔧 Environment variables check:")
    logger.info(f"   QDRANT_HOST env: {os.getenv('QDRANT_HOST', 'NOT SET')}")
    logger.info(f"   QDRANT_PORT env: {os.getenv('QDRANT_PORT', 'NOT SET')}")
    logger.info(f"   QDRANT_HTTPS env: {os.getenv('QDRANT_HTTPS', 'NOT SET')}")

    try:
        # Preparar parámetros de conexión
        connection_params = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "grpc_port": settings.qdrant_grpc_port,
            "prefer_grpc": settings.qdrant_prefer_grpc,
            "https": settings.qdrant_https,
            "timeout": settings.qdrant_timeout
        }

        # Agregar API key solo si está configurada
        if settings.qdrant_api_key:
            connection_params["api_key"] = "***"  # No mostrar la key completa
            logger.info("🔑 Qdrant API key configured")

        # Log de configuración de conexión
        protocol = "https" if settings.qdrant_https else "http"
        connection_url = f"{protocol}://{settings.qdrant_host}:{settings.qdrant_port}"

        logger.info("=" * 60)
        logger.info("🔌 Connecting to Qdrant...")
        logger.info(f"   Host: {settings.qdrant_host}")
        logger.info(f"   HTTP Port: {settings.qdrant_port}")
        logger.info(f"   gRPC Port: {settings.qdrant_grpc_port}")
        logger.info(f"   HTTPS: {settings.qdrant_https}")
        logger.info(f"   Prefer gRPC: {settings.qdrant_prefer_grpc}")
        logger.info(f"   Timeout: {settings.qdrant_timeout}s")
        logger.info(f"   API Key: {'Yes' if settings.qdrant_api_key else 'No'}")
        logger.info(f"   Full URL: {connection_url}")
        logger.info("=" * 60)

        # Test DNS resolution primero
        import socket
        try:
            logger.info(f"🔍 Resolving DNS for {settings.qdrant_host}...")
            ip_addresses = socket.getaddrinfo(settings.qdrant_host, settings.qdrant_port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            logger.info(f"✓ DNS resolved to: {[addr[4][0] for addr in ip_addresses]}")
        except socket.gaierror as dns_error:
            logger.error(f"❌ DNS resolution failed: {dns_error}")
            logger.error(f"   Cannot resolve host: {settings.qdrant_host}")
            return False
        except Exception as dns_error:
            logger.warning(f"⚠️ DNS check error (continuing anyway): {dns_error}")

        # Usar la API key real para la conexión
        if settings.qdrant_api_key:
            connection_params["api_key"] = settings.qdrant_api_key

        qdrant_client = AsyncQdrantClient(**connection_params)
        logger.info("✓ Qdrant client instance created")

        # Test connection con timeout
        try:
            logger.info("🔍 Testing connection...")
            collections = await qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]

            logger.info("=" * 60)
            logger.info("✅ Successfully connected to Qdrant!")
            logger.info(f"   Total collections: {len(collection_names)}")
            if collection_names:
                logger.info(f"   Collections: {', '.join(collection_names)}")
            else:
                logger.info("   Collections: (none yet)")
            logger.info("=" * 60)
            return True
        except Exception as test_error:
            logger.error("=" * 60)
            logger.error("❌ Connection test FAILED")
            logger.error(f"   Error type: {type(test_error).__name__}")
            logger.error(f"   Error message: {str(test_error)}")
            logger.error(f"   Error repr: {repr(test_error)}")

            # Log del traceback completo
            import traceback
            logger.error(f"   Full traceback:")
            for line in traceback.format_exception(type(test_error), test_error, test_error.__traceback__):
                logger.error(f"     {line.rstrip()}")

            logger.error("=" * 60)
            await qdrant_client.close()
            qdrant_client = None
            return False

    except Exception as e:
        error_type = type(e).__name__
        logger.error("=" * 60)
        logger.error("❌ Failed to initialize Qdrant client")
        logger.error(f"   Host: {settings.qdrant_host}")
        logger.error(f"   HTTP Port: {settings.qdrant_port}")
        logger.error(f"   gRPC Port: {settings.qdrant_grpc_port}")
        logger.error(f"   Error type: {error_type}")
        logger.error(f"   Error details: {str(e)}")
        logger.error("=" * 60)

        # Información adicional basada en el tipo de error
        if "ConnectionRefusedError" in error_type:
            logger.error("💡 Troubleshooting:")
            logger.error("   - Verify Qdrant service is running")
            logger.error("   - Check host and port configuration")
            logger.error("   - Verify firewall/network allows connection")
        elif "Timeout" in error_type:
            logger.error("💡 Troubleshooting:")
            logger.error("   - Check if Qdrant is reachable from this network")
            logger.error("   - Verify there are no network issues")
            logger.error("   - Check if server is overloaded")

        logger.debug(f"Full traceback:", exc_info=True)

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
