"""REST endpoints for AI-powered product detection from images."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from services.product_detection_service import (
    DetectedProductList,
    detect_from_menu,
    detect_from_showcase,
)
from utils.auth import get_current_user_id_from_header
from utils.rate_limit import RATE_LIMIT_UPLOADS, limiter

router = APIRouter(prefix="/products", tags=["Product Detection"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


async def _read_and_validate_image(file: UploadFile) -> tuple[bytes, str]:
    """Read and validate an uploaded image file."""
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de imagen no permitido. Permitidos: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío",
        )

    if len(file_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen es muy grande. Máximo: 10MB",
        )

    return file_bytes, content_type


@router.post(
    "/detect-from-showcase",
    response_model=DetectedProductList,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def detect_products_from_showcase(
    request: Request,
    file: UploadFile = File(..., description="Foto de vitrina, estante o exhibidor"),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Detectar productos desde una foto de vitrina/estante/exhibidor.

    Analiza la imagen con IA y retorna un listado de productos detectados.
    No guarda nada en la base de datos.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_bytes, content_type = await _read_and_validate_image(file)

    try:
        result = await detect_from_showcase(file_bytes, content_type)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar la imagen: {str(exc)}",
        ) from exc

    return result


@router.post(
    "/detect-from-menu",
    response_model=DetectedProductList,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def detect_products_from_menu(
    request: Request,
    file: UploadFile = File(..., description="Foto de menú, carta o lista de precios"),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Detectar productos desde una foto de menú/carta/lista de precios.

    Analiza la imagen con IA y retorna un listado de productos con precios.
    No guarda nada en la base de datos.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_bytes, content_type = await _read_and_validate_image(file)

    try:
        result = await detect_from_menu(file_bytes, content_type)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar el menú: {str(exc)}",
        ) from exc

    return result
