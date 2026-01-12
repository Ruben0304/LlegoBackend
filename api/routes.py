"""REST API routes - Only essential endpoints that can't be done via GraphQL."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from typing import Optional
from pydantic import BaseModel

from .endpoints.uploads import router as uploads_router
from .endpoints.apple_auth import router as apple_auth_router
from .endpoints.error_logs import router as error_logs_router
from .endpoints.device_tokens import router as device_tokens_router
from repositories import auth_repo
from utils.auth import create_access_token
from utils.rate_limit import limiter, RATE_LIMIT_AUTH
from services.payments import validate_payment_image_with_transfer_id
from core.config import settings

router = APIRouter()
router.include_router(uploads_router)
router.include_router(apple_auth_router)
router.include_router(error_logs_router)
router.include_router(device_tokens_router)


# =============================================================================
# Authentication Models (for development endpoints)
# =============================================================================

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    phone: Optional[str] = None


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


# =============================================================================
# Authentication Endpoints (Development Only)
# Production uses GraphQL: loginWithGoogle, loginWithApple
# =============================================================================

@router.post("/auth/register", response_model=AuthResponse, tags=["Authentication (Dev)"])
@limiter.limit(RATE_LIMIT_AUTH)
async def register(request: Request, data: RegisterRequest):
    """
    [DEV ONLY] Register with email/password.
    Production: Use GraphQL loginWithGoogle or loginWithApple.
    """
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Not found")
    
    existing_user = await auth_repo.get_user_by_email(data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await auth_repo.create_user(
        name=data.name,
        email=data.email,
        password=data.password,
        phone=data.phone,
        role="customer"
    )

    access_token = create_access_token(data={
        "sub": user.email,
        "user_id": user.id,
        "role": user.role
    })

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


@router.post("/auth/login", response_model=AuthResponse, tags=["Authentication (Dev)"])
@limiter.limit(RATE_LIMIT_AUTH)
async def login(request: Request, data: LoginRequest):
    """
    [DEV ONLY] Login with email/password.
    Production: Use GraphQL loginWithGoogle or loginWithApple.
    """
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Not found")
    
    user = await auth_repo.authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={
        "sub": user.email,
        "user_id": user.id,
        "role": user.role
    })

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


# =============================================================================
# Payment Validation Endpoint
# =============================================================================

@router.post(
    "/payments/validate",
    response_model=PaymentValidationResponse,
    tags=["Payments"],
)
async def validate_payment_image(
    transfer_id: str = Form(..., description="ID de transferencia proporcionado por el cliente"),
    file: UploadFile = File(..., description="Captura del SMS bancario"),
):
    """Validate a payment image using Gemini OCR."""
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
        raise HTTPException(status_code=500, detail="Error al procesar la imagen") from exc

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
