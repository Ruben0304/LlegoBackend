"""Qdrant client singleton."""
import sys
import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, VectorParams
from typing import Optional, Dict, Any
from core.config import settings

# Configurar logger
logger = logging.getLogger(__name__)

# Global Qdrant client instance
qdrant_client: Optional[QdrantClient] = None


def connect_to_qdrant():
    """Connect to Qdrant (optional - won't fail startup if unavailable)"""
    global qdrant_client
    
    connection_info = f"{settings.qdrant_host}:{settings.qdrant_port}"
    logger.info(f"Attempting to connect to Qdrant at {connection_info}")
    
    try:
        # Mostrar configuración de conexión (sin credenciales sensibles)
        logger.debug(f"Qdrant connection settings - Host: {settings.qdrant_host}, Port: {settings.qdrant_port}")
        
        qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            # Habilita logs detallados para depuración
            # https://qdrant.tech/documentation/concepts/logging/
            debug=True
        )
        
        # Test connection con timeout
        try:
            collections = qdrant_client.get_collections()
            logger.info(f"✓ Successfully connected to Qdrant at {connection_info}")
            logger.debug(f"Available collections: {[c.name for c in collections.collections]}")
            return True
        except Exception as test_error:
            logger.error(f"❌ Connection test failed for Qdrant at {connection_info}")
            logger.error(f"Error details: {str(test_error)}", exc_info=True)
            qdrant_client = None
            return False
            
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"❌ Failed to initialize Qdrant connection to {connection_info}")
        logger.error(f"Error type: {error_type}")
        logger.error(f"Error details: {str(e)}", exc_info=True)
        
        # Información adicional basada en el tipo de error
        if "ConnectionRefusedError" in error_type:
            logger.error("🛑 Connection was refused. Please check if:"
                       "\n  - Qdrant server is running"
                       "\n  - Host and port are correct"
                       "\n  - Firewall allows the connection")
        elif "Timeout" in error_type:
            logger.error("⏱️ Connection timed out. Please check if:"
                       "\n  - The Qdrant server is reachable from this network"
                       "\n  - There are no network issues"
                       "\n  - The server is not overloaded")
        
        qdrant_client = None
        return False


def close_qdrant_connection():
    """Close Qdrant connection"""
    global qdrant_client
    if qdrant_client:
        try:
            qdrant_client.close()
            logger.info("✓ Qdrant connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing Qdrant connection: {str(e)}", exc_info=True)
        finally:
            qdrant_client = None


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client instance"""
    if qdrant_client is None:
        logger.error("Qdrant client not initialized. Call connect_to_qdrant() first.")
        raise RuntimeError("Qdrant client not initialized. Call connect_to_qdrant() first.")
    
    # Verificar si la conexión sigue activa
    try:
        qdrant_client.get_collections()
    except Exception as e:
        logger.error("Qdrant connection lost. Attempting to reconnect...")
        connect_to_qdrant()
        if qdrant_client is None:
            logger.critical("Failed to re-establish Qdrant connection")
            raise RuntimeError("Failed to re-establish Qdrant connection")
    
    return qdrant_client


def create_collection(
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
        collections = client.get_collections()
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
        result = client.create_collection(**create_params)
        
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
