"""Qdrant client singleton."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from typing import Optional
from core.config import settings

# Global Qdrant client instance
qdrant_client: Optional[QdrantClient] = None


def connect_to_qdrant():
    """Connect to Qdrant (optional - won't fail startup if unavailable)"""
    global qdrant_client
    try:
        qdrant_client = QdrantClient(url=f"{settings.qdrant_host}:{settings.qdrant_port}")
        # Test connection
        qdrant_client.get_collections()
        print(f"✓ Connected to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
    except Exception as e:
        print(f"⚠ Qdrant not available at {settings.qdrant_host}:{settings.qdrant_port}")
        print(f"  Vector search features will be disabled until Qdrant is running")
        qdrant_client = None


def close_qdrant_connection():
    """Close Qdrant connection"""
    global qdrant_client
    if qdrant_client:
        qdrant_client.close()
        print("✓ Qdrant connection closed")


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client instance"""
    if qdrant_client is None:
        raise RuntimeError("Qdrant client not initialized. Call connect_to_qdrant() first.")
    return qdrant_client


def create_collection(
    collection_name: str,
    vector_size: int = 768,
    distance: Distance = Distance.COSINE
):
    """
    Create a new collection in Qdrant.

    Args:
        collection_name: Name of the collection
        vector_size: Dimension of vectors (default: 768)
        distance: Distance metric (default: Distance.COSINE)
    """
    client = get_qdrant_client()

    try:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance
            )
        )
        print(f"✓ Created Qdrant collection: {collection_name} (size={vector_size}, distance={distance.value})")
        return True
    except Exception as e:
        print(f"✗ Error creating collection {collection_name}: {e}")
        raise
