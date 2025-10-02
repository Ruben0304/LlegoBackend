"""REST API endpoints."""
from fastapi import APIRouter, Query, HTTPException
from typing import List
import uuid

from models import (
    User,
    Business,
    Branch,
    Product,
    users_repo,
    businesses_repo,
    branches_repo,
    products_repo,
)

router = APIRouter()


@router.get("/users", response_model=List[User], tags=["Users"])
async def list_users():
    """Get all users."""
    return await users_repo.get_all()


@router.get("/businesses", response_model=List[Business], tags=["Businesses"])
async def list_businesses():
    """Get all businesses."""
    return await businesses_repo.get_all()


@router.get("/branches", response_model=List[Branch], tags=["Branches"])
async def list_branches():
    """Get all branches."""
    return await branches_repo.get_all()


@router.get("/products", response_model=List[Product], tags=["Products"])
async def list_products():
    """Get all products."""
    return await products_repo.get_all()


# Embedding Test Endpoint
@router.post("/embeddings/test", tags=["Embeddings"])
async def test_embedding(text: str = Query(..., description="Text to vectorize")):
    """
    Test endpoint to generate embedding from text.

    Returns the vector representation of the input text.
    """
    from services.embeddings.gemini_service import GeminiEmbeddingService

    embedding_service = GeminiEmbeddingService()
    embedding = embedding_service.generate_embedding(text)

    return {
        "text": text,
        "embedding": embedding,
        "dimension": len(embedding)
    }


# Qdrant Collection Management
@router.post("/qdrant/collections", tags=["Qdrant"])
async def create_qdrant_collection(
    collection_name: str = Query(..., description="Name of the collection"),
    vector_size: int = Query(768, description="Dimension of vectors"),
    distance: str = Query("Cosine", description="Distance metric: Cosine, Euclid, Dot, Manhattan")
):
    """
    Create a new collection in Qdrant.

    Parameters:
    - collection_name: Name of the collection to create
    - vector_size: Dimension of vectors (default: 768)
    - distance: Distance metric (Cosine, Euclid, Dot, Manhattan)
    """
    from qdrant_client.models import Distance
    from clients import create_collection

    # Map string to Distance enum
    distance_map = {
        "Cosine": Distance.COSINE,
        "Euclid": Distance.EUCLID,
        "Dot": Distance.DOT,
        "Manhattan": Distance.MANHATTAN
    }

    if distance not in distance_map:
        return {
            "error": f"Invalid distance metric. Use: {', '.join(distance_map.keys())}"
        }

    try:
        create_collection(
            collection_name=collection_name,
            vector_size=vector_size,
            distance=distance_map[distance]
        )

        return {
            "status": "success",
            "collection_name": collection_name,
            "vector_size": vector_size,
            "distance": distance
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# Vectorize Products
@router.post("/vectorize/products", tags=["Vectorization"])
async def vectorize_all_products():
    """
    Vectorize all products and store them in Qdrant.

    Vectorizes only the 'name' attribute of each product.
    Processes products one by one (no batch processing).
    """
    from services.embeddings.gemini_service import GeminiEmbeddingService
    from clients import get_qdrant_client
    from qdrant_client.models import PointStruct

    try:
        # Get all products
        products = await products_repo.get_all()

        if not products:
            return {
                "status": "success",
                "message": "No products found to vectorize",
                "total": 0,
                "vectorized": 0
            }

        # Initialize services
        embedding_service = GeminiEmbeddingService()
        qdrant_client = get_qdrant_client()

        collection_name = "products"
        vectorized_count = 0
        errors = []

        # Ensure collection exists
        try:
            qdrant_client.get_collection(collection_name)
        except:
            from clients import create_collection
            create_collection(collection_name=collection_name, vector_size=768)

        # Process each product one by one
        for product in products:
            try:
                # Generate embedding for product name
                embedding = embedding_service.generate_embedding(product.name)

                # Generate UUID from MongoDB ObjectID
                point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, product.id))

                # Create point for Qdrant
                point = PointStruct(
                    id=point_uuid,
                    vector=embedding,
                    payload={
                        "id": product.id
                    }
                )

                # Upsert to Qdrant
                qdrant_client.upsert(
                    collection_name=collection_name,
                    points=[point]
                )

                vectorized_count += 1

            except Exception as e:
                errors.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "error": str(e)
                })

        return {
            "status": "success",
            "total": len(products),
            "vectorized": vectorized_count,
            "errors": errors if errors else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Vectorize Branches
@router.post("/vectorize/branches", tags=["Vectorization"])
async def vectorize_all_branches():
    """
    Vectorize all branches and store them in Qdrant.

    Vectorizes 'name' and 'address' attributes of each branch.
    Processes branches one by one (no batch processing).
    """
    from services.embeddings.gemini_service import GeminiEmbeddingService
    from clients import get_qdrant_client
    from qdrant_client.models import PointStruct

    try:
        # Get all branches
        branches = await branches_repo.get_all()

        if not branches:
            return {
                "status": "success",
                "message": "No branches found to vectorize",
                "total": 0,
                "vectorized": 0
            }

        # Initialize services
        embedding_service = GeminiEmbeddingService()
        qdrant_client = get_qdrant_client()

        collection_name = "branches"
        vectorized_count = 0
        errors = []

        # Ensure collection exists
        try:
            qdrant_client.get_collection(collection_name)
        except:
            from clients import create_collection
            create_collection(collection_name=collection_name, vector_size=768)

        # Process each branch one by one
        for branch in branches:
            try:
                # Combine name and address for embedding
                text_to_vectorize = f"{branch.name} {branch.address}"

                # Generate embedding
                embedding = embedding_service.generate_embedding(text_to_vectorize)

                # Generate UUID from MongoDB ObjectID
                point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, branch.id))

                # Create point for Qdrant
                point = PointStruct(
                    id=point_uuid,
                    vector=embedding,
                    payload={
                        "id": branch.id
                    }
                )

                # Upsert to Qdrant
                qdrant_client.upsert(
                    collection_name=collection_name,
                    points=[point]
                )

                vectorized_count += 1

            except Exception as e:
                errors.append({
                    "branch_id": branch.id,
                    "branch_name": branch.name,
                    "error": str(e)
                })

        return {
            "status": "success",
            "total": len(branches),
            "vectorized": vectorized_count,
            "errors": errors if errors else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
