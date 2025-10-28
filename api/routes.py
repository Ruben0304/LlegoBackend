"""REST API endpoints."""
from fastapi import APIRouter, Query, HTTPException, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
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
from repositories import auth_repo
from utils.auth import create_access_token
from services.payments import validate_payment_image_with_transfer_id

router = APIRouter()


# Request/Response models for authentication
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "customer"


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class PaymentValidationResponse(BaseModel):
    matched: bool
    message: str
    detected_transfer_id: str
    extracted_data: dict
    saved_payment: Optional[dict] = None


@router.post("/auth/register", response_model=AuthResponse, tags=["Authentication"])
async def register(request: RegisterRequest):
    """Register a new user with email and password."""
    # Check if user already exists
    existing_user = await auth_repo.get_user_by_email(request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create new user
    user = await auth_repo.create_user(
        name=request.name,
        email=request.email,
        password=request.password,
        phone=request.phone,
        role=request.role or "customer"
    )

    # Create access token
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

    return AuthResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "createdAt": user.createdAt.isoformat()
        }
    )


@router.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(request: LoginRequest):
    """Login with email and password."""
    # Authenticate user
    user = await auth_repo.authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create access token
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

    return AuthResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "createdAt": user.createdAt.isoformat()
        }
    )


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


@router.post(
    "/payments/validate",
    response_model=PaymentValidationResponse,
    tags=["Payments"],
)
async def validate_payment_image(
    transfer_id: str = Form(..., description="ID de transferencia proporcionado por el cliente"),
    file: UploadFile = File(..., description="Captura del SMS bancario"),
):
    """Validate a payment image using Gemini OCR and persist it when the transfer ID matches."""
    try:
        file_bytes = await file.read()
        content_type = file.content_type or "image/jpeg"
        result = await validate_payment_image_with_transfer_id(
            file_bytes=file_bytes,
            content_type=content_type,
            transfer_id=transfer_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al procesar la imagen: {exc}") from exc

    return PaymentValidationResponse(
        matched=result.matched,
        message=result.message,
        detected_transfer_id=result.detected_transfer_id,
        extracted_data=result.extracted_data.model_dump(),
        saved_payment=(
            result.saved_payment.model_dump(by_alias=True)
            if result.saved_payment
            else None
        ),
    )


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
    from clients import create_collection, get_qdrant_client

    # Map string to Distance enum
    distance_map = {
        "Cosine": Distance.COSINE,
        "Euclid": Distance.EUCLID,
        "Dot": Distance.DOT,
        "Manhattan": Distance.MANHATTAN
    }

    # Validate distance metric
    if distance not in distance_map:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid distance metric",
                "provided": distance,
                "valid_options": list(distance_map.keys()),
                "message": f"Distance must be one of: {', '.join(distance_map.keys())}"
            }
        )

    # Validate vector size
    if vector_size <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid vector size",
                "provided": vector_size,
                "message": "Vector size must be a positive integer"
            }
        )

    # Validate collection name
    if not collection_name or not collection_name.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid collection name",
                "message": "Collection name cannot be empty"
            }
        )

    try:
        # Check if Qdrant client is initialized
        try:
            client = get_qdrant_client()
        except RuntimeError as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Qdrant service unavailable",
                    "message": "Qdrant client is not initialized. Service may be offline.",
                    "troubleshooting": [
                        "Verify Qdrant service is running",
                        "Check QDRANT_HOST and QDRANT_PORT environment variables",
                        "Review application logs for connection errors"
                    ]
                }
            )

        # Check if collection already exists
        collections = await client.get_collections()
        existing_collections = [c.name for c in collections.collections]

        if collection_name in existing_collections:
            # Get collection info
            collection_info = await client.get_collection(collection_name)
            return {
                "status": "already_exists",
                "message": f"Collection '{collection_name}' already exists",
                "collection_name": collection_name,
                "existing_config": {
                    "vector_size": collection_info.config.params.vectors.size,
                    "distance": collection_info.config.params.vectors.distance.value,
                    "points_count": collection_info.points_count
                },
                "requested_config": {
                    "vector_size": vector_size,
                    "distance": distance
                }
            }

        # Create the collection
        success = await create_collection(
            collection_name=collection_name,
            vector_size=vector_size,
            distance=distance_map[distance]
        )

        if success:
            return {
                "status": "created",
                "message": f"Collection '{collection_name}' created successfully",
                "collection_name": collection_name,
                "config": {
                    "vector_size": vector_size,
                    "distance": distance,
                    "points_count": 0
                },
                "next_steps": [
                    f"Use POST /vectorize/products to add product vectors" if collection_name == "products" else None,
                    f"Use POST /vectorize/branches to add branch vectors" if collection_name == "branches" else None,
                    f"Collection is ready to accept vector data"
                ]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Collection creation failed",
                    "message": f"Failed to create collection '{collection_name}' - operation returned False"
                }
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)

        # Provide specific error handling based on error type
        if "already exists" in error_message.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Collection already exists",
                    "collection_name": collection_name,
                    "message": f"Collection '{collection_name}' already exists in Qdrant"
                }
            )
        elif "timeout" in error_message.lower():
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "Qdrant timeout",
                    "message": "Operation timed out while connecting to Qdrant",
                    "troubleshooting": [
                        "Check if Qdrant service is responsive",
                        "Verify network connectivity",
                        "Check Qdrant server logs for issues"
                    ]
                }
            )
        elif "connection" in error_message.lower():
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Qdrant connection error",
                    "message": "Failed to connect to Qdrant service",
                    "error_details": error_message,
                    "troubleshooting": [
                        "Verify Qdrant service is running",
                        "Check QDRANT_HOST and QDRANT_PORT configuration",
                        "Verify firewall/network allows connection"
                    ]
                }
            )
        else:
            # Generic error
            raise HTTPException(
                status_code=500,
                detail={
                    "error": error_type,
                    "message": f"Failed to create collection '{collection_name}'",
                    "error_details": error_message,
                    "parameters": {
                        "collection_name": collection_name,
                        "vector_size": vector_size,
                        "distance": distance
                    }
                }
            )


# Vectorize Products
@router.post("/vectorize/products", tags=["Vectorization"])
async def vectorize_all_products():
    """
    Vectorize all products and store them in Qdrant.

    Vectorizes only the 'name' attribute of each product.
    Processes products one by one (no batch processing).
    """
    from services.embeddings.gemini_service import GeminiEmbeddingService
    from clients import get_qdrant_client, create_collection
    from qdrant_client.models import PointStruct, Distance

    collection_name = "products"

    try:
        # Check if Qdrant client is initialized
        try:
            qdrant_client = get_qdrant_client()
        except RuntimeError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Qdrant service unavailable",
                    "message": "Qdrant client is not initialized. Service may be offline.",
                    "troubleshooting": [
                        "Verify Qdrant service is running",
                        "Check QDRANT_HOST and QDRANT_PORT environment variables",
                        "Review application logs for connection errors"
                    ]
                }
            )

        # Get all products from MongoDB
        products = await products_repo.get_all()

        if not products:
            return {
                "status": "no_data",
                "message": "No products found in database to vectorize",
                "total": 0,
                "vectorized": 0,
                "collection": collection_name,
                "suggestion": "Add products to MongoDB first using POST /products endpoint"
            }

        # Initialize embedding service
        try:
            embedding_service = GeminiEmbeddingService()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Embedding service unavailable",
                    "message": "Failed to initialize Gemini embedding service",
                    "error_details": str(e),
                    "troubleshooting": [
                        "Check GEMINI_API_KEY environment variable",
                        "Verify Google AI API quota and access",
                        "Review application logs for API errors"
                    ]
                }
            )

        # Ensure collection exists
        collection_created = False
        try:
            await qdrant_client.get_collection(collection_name)
        except Exception:
            try:
                collection_created = await create_collection(
                    collection_name=collection_name,
                    vector_size=768,
                    distance=Distance.COSINE
                )
                if not collection_created:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "Collection creation failed",
                            "message": f"Failed to create collection '{collection_name}'",
                            "collection": collection_name
                        }
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Collection setup failed",
                        "message": f"Could not verify or create collection '{collection_name}'",
                        "error_details": str(e),
                        "collection": collection_name
                    }
                )

        # Process each product one by one
        vectorized_count = 0
        errors = []
        skipped = []

        for idx, product in enumerate(products, 1):
            try:
                # Validate product has name
                if not product.name or not product.name.strip():
                    skipped.append({
                        "product_id": product.id,
                        "reason": "Empty or missing product name"
                    })
                    continue

                # Generate embedding for product name
                try:
                    embedding = embedding_service.generate_embedding(product.name)
                except Exception as embed_error:
                    errors.append({
                        "product_id": product.id,
                        "product_name": product.name,
                        "stage": "embedding_generation",
                        "error": str(embed_error)
                    })
                    continue

                # Generate UUID from MongoDB ObjectID
                point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, product.id))

                # Create point for Qdrant
                point = PointStruct(
                    id=point_uuid,
                    vector=embedding,
                    payload={
                        "id": product.id,
                        "name": product.name
                    }
                )

                # Upsert to Qdrant
                try:
                    await qdrant_client.upsert(
                        collection_name=collection_name,
                        points=[point]
                    )
                    vectorized_count += 1
                except Exception as upsert_error:
                    errors.append({
                        "product_id": product.id,
                        "product_name": product.name,
                        "stage": "qdrant_upsert",
                        "error": str(upsert_error)
                    })

            except Exception as e:
                errors.append({
                    "product_id": product.id,
                    "product_name": getattr(product, 'name', 'unknown'),
                    "stage": "processing",
                    "error": str(e)
                })

        # Calculate success rate
        total_processed = len(products)
        success_rate = (vectorized_count / total_processed * 100) if total_processed > 0 else 0

        # Determine overall status
        if vectorized_count == 0:
            status = "failed"
        elif errors or skipped:
            status = "partial_success"
        else:
            status = "success"

        response = {
            "status": status,
            "message": f"Vectorized {vectorized_count} of {total_processed} products ({success_rate:.1f}% success rate)",
            "collection": collection_name,
            "collection_created": collection_created,
            "summary": {
                "total_products": total_processed,
                "vectorized": vectorized_count,
                "errors": len(errors),
                "skipped": len(skipped),
                "success_rate": f"{success_rate:.1f}%"
            }
        }

        if errors:
            response["errors"] = errors[:10]  # Limit to first 10 errors
            if len(errors) > 10:
                response["errors_truncated"] = f"Showing 10 of {len(errors)} errors"

        if skipped:
            response["skipped"] = skipped[:10]  # Limit to first 10 skipped
            if len(skipped) > 10:
                response["skipped_truncated"] = f"Showing 10 of {len(skipped)} skipped items"

        if status == "success":
            response["next_steps"] = [
                "Use vector search endpoint to query products",
                "Verify vectors with Qdrant dashboard or API"
            ]
        elif status == "partial_success":
            response["recommendations"] = [
                "Review errors to identify issues",
                "Retry vectorization for failed products",
                "Check product data quality in MongoDB"
            ]
        elif status == "failed":
            response["recommendations"] = [
                "Check all error details above",
                "Verify embedding service is working (test with /embeddings/test)",
                "Verify Qdrant collection is accessible",
                "Check application logs for detailed errors"
            ]

        return response

    except HTTPException:
        raise
    except Exception as e:
        error_type = type(e).__name__
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_type,
                "message": "Unexpected error during product vectorization",
                "error_details": str(e),
                "collection": collection_name,
                "troubleshooting": [
                    "Check application logs for full error trace",
                    "Verify MongoDB connection is stable",
                    "Verify Qdrant service is running",
                    "Verify Gemini API is accessible"
                ]
            }
        )


# Vectorize Branches
@router.post("/vectorize/branches", tags=["Vectorization"])
async def vectorize_all_branches():
    """
    Vectorize all branches and store them in Qdrant.

    Vectorizes 'name' and 'address' attributes of each branch.
    Processes branches one by one (no batch processing).
    """
    from services.embeddings.gemini_service import GeminiEmbeddingService
    from clients import get_qdrant_client, create_collection
    from qdrant_client.models import PointStruct, Distance

    collection_name = "branches"

    try:
        # Check if Qdrant client is initialized
        try:
            qdrant_client = get_qdrant_client()
        except RuntimeError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Qdrant service unavailable",
                    "message": "Qdrant client is not initialized. Service may be offline.",
                    "troubleshooting": [
                        "Verify Qdrant service is running",
                        "Check QDRANT_HOST and QDRANT_PORT environment variables",
                        "Review application logs for connection errors"
                    ]
                }
            )

        # Get all branches from MongoDB
        branches = await branches_repo.get_all()

        if not branches:
            return {
                "status": "no_data",
                "message": "No branches found in database to vectorize",
                "total": 0,
                "vectorized": 0,
                "collection": collection_name,
                "suggestion": "Add branches to MongoDB first using POST /branches endpoint"
            }

        # Initialize embedding service
        try:
            embedding_service = GeminiEmbeddingService()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Embedding service unavailable",
                    "message": "Failed to initialize Gemini embedding service",
                    "error_details": str(e),
                    "troubleshooting": [
                        "Check GEMINI_API_KEY environment variable",
                        "Verify Google AI API quota and access",
                        "Review application logs for API errors"
                    ]
                }
            )

        # Ensure collection exists
        collection_created = False
        try:
            await qdrant_client.get_collection(collection_name)
        except Exception:
            try:
                collection_created = await create_collection(
                    collection_name=collection_name,
                    vector_size=768,
                    distance=Distance.COSINE
                )
                if not collection_created:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "Collection creation failed",
                            "message": f"Failed to create collection '{collection_name}'",
                            "collection": collection_name
                        }
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Collection setup failed",
                        "message": f"Could not verify or create collection '{collection_name}'",
                        "error_details": str(e),
                        "collection": collection_name
                    }
                )

        # Process each branch one by one
        vectorized_count = 0
        errors = []
        skipped = []

        for idx, branch in enumerate(branches, 1):
            try:
                # Validate branch has name and address
                if not branch.name or not branch.name.strip():
                    skipped.append({
                        "branch_id": branch.id,
                        "reason": "Empty or missing branch name"
                    })
                    continue

                if not branch.address or not branch.address.strip():
                    skipped.append({
                        "branch_id": branch.id,
                        "branch_name": branch.name,
                        "reason": "Empty or missing branch address"
                    })
                    continue

                # Combine name and address for embedding
                text_to_vectorize = f"{branch.name} {branch.address}"

                # Generate embedding
                try:
                    embedding = embedding_service.generate_embedding(text_to_vectorize)
                except Exception as embed_error:
                    errors.append({
                        "branch_id": branch.id,
                        "branch_name": branch.name,
                        "stage": "embedding_generation",
                        "error": str(embed_error)
                    })
                    continue

                # Generate UUID from MongoDB ObjectID
                point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, branch.id))

                # Create point for Qdrant
                point = PointStruct(
                    id=point_uuid,
                    vector=embedding,
                    payload={
                        "id": branch.id,
                        "name": branch.name,
                        "address": branch.address
                    }
                )

                # Upsert to Qdrant
                try:
                    await qdrant_client.upsert(
                        collection_name=collection_name,
                        points=[point]
                    )
                    vectorized_count += 1
                except Exception as upsert_error:
                    errors.append({
                        "branch_id": branch.id,
                        "branch_name": branch.name,
                        "stage": "qdrant_upsert",
                        "error": str(upsert_error)
                    })

            except Exception as e:
                errors.append({
                    "branch_id": branch.id,
                    "branch_name": getattr(branch, 'name', 'unknown'),
                    "stage": "processing",
                    "error": str(e)
                })

        # Calculate success rate
        total_processed = len(branches)
        success_rate = (vectorized_count / total_processed * 100) if total_processed > 0 else 0

        # Determine overall status
        if vectorized_count == 0:
            status = "failed"
        elif errors or skipped:
            status = "partial_success"
        else:
            status = "success"

        response = {
            "status": status,
            "message": f"Vectorized {vectorized_count} of {total_processed} branches ({success_rate:.1f}% success rate)",
            "collection": collection_name,
            "collection_created": collection_created,
            "summary": {
                "total_branches": total_processed,
                "vectorized": vectorized_count,
                "errors": len(errors),
                "skipped": len(skipped),
                "success_rate": f"{success_rate:.1f}%"
            }
        }

        if errors:
            response["errors"] = errors[:10]  # Limit to first 10 errors
            if len(errors) > 10:
                response["errors_truncated"] = f"Showing 10 of {len(errors)} errors"

        if skipped:
            response["skipped"] = skipped[:10]  # Limit to first 10 skipped
            if len(skipped) > 10:
                response["skipped_truncated"] = f"Showing 10 of {len(skipped)} skipped items"

        if status == "success":
            response["next_steps"] = [
                "Use vector search endpoint to query branches",
                "Verify vectors with Qdrant dashboard or API"
            ]
        elif status == "partial_success":
            response["recommendations"] = [
                "Review errors to identify issues",
                "Retry vectorization for failed branches",
                "Check branch data quality in MongoDB"
            ]
        elif status == "failed":
            response["recommendations"] = [
                "Check all error details above",
                "Verify embedding service is working (test with /embeddings/test)",
                "Verify Qdrant collection is accessible",
                "Check application logs for detailed errors"
            ]

        return response

    except HTTPException:
        raise
    except Exception as e:
        error_type = type(e).__name__
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_type,
                "message": "Unexpected error during branch vectorization",
                "error_details": str(e),
                "collection": collection_name,
                "troubleshooting": [
                    "Check application logs for full error trace",
                    "Verify MongoDB connection is stable",
                    "Verify Qdrant service is running",
                    "Verify Gemini API is accessible"
                ]
            }
        )
