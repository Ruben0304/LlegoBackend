"""REST endpoints for user operations."""

from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from repositories import users_repo
from services.image_processing import process_image_for_store_async
from utils.auth import get_current_user_id_from_header
from utils.rate_limit import RATE_LIMIT_UPLOADS, limiter
from utils.s3 import delete_file, generate_presigned_url, upload_file

router = APIRouter(prefix="/users", tags=["Users"])

# =============================================================================
# Security Configuration
# =============================================================================

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

MAX_AVATAR_SIZE = 10 * 1024 * 1024  # 10MB


def validate_image_signature(content: bytes) -> str | None:
    """Validate image by checking magic bytes."""
    if len(content) < 12:
        return None

    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    return None


async def validate_upload(image: UploadFile, max_size: int) -> bytes:
    """Comprehensive upload validation."""
    # Validate Content-Type header
    content_type = image.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no permitido. Permitidos: JPEG, PNG, WebP, GIF",
        )

    # Read file with size limit
    chunks = []
    total_size = 0
    chunk_size = 64 * 1024  # 64KB chunks

    while True:
        chunk = await image.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)

        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo muy grande. Máximo: {max_size // (1024 * 1024)}MB",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío"
        )

    # Validate magic bytes
    detected_type = validate_image_signature(content)
    if not detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es una imagen válida",
        )

    # Verify with PIL
    try:
        from PIL import Image

        img = Image.open(BytesIO(content))
        img.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Imagen corrupta o inválida"
        )

    return content


# =============================================================================
# User Endpoints
# =============================================================================


@router.put("/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def update_user_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Update user avatar image.

    This endpoint:
    1. Validates and processes the uploaded image
    2. Uploads it to S3
    3. Deletes the old avatar if it exists
    4. Updates the user record in the database

    Max size: 10MB | Output: 400x400 JPG

    Returns:
        - id: User ID
        - avatar: S3 path to the avatar
        - avatar_url: Presigned URL to access the avatar
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    # Get current user to check for existing avatar
    user = await users_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validate and read the image
    file_content = await validate_upload(image, MAX_AVATAR_SIZE)

    # Process the image (resize to 400x400, convert to JPG)
    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "user_avatar", convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error procesando imagen: {str(e)}"
        )

    # Upload to S3
    try:
        image_path = await upload_file(
            processed_content, "users/avatars", user_id, extension
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error subiendo imagen: {str(e)}")

    # Delete old avatar if exists
    if user.avatar:
        try:
            await delete_file(user.avatar)
        except Exception:
            # Log but don't fail if old avatar deletion fails
            pass

    # Update user in database
    try:
        updated_user = await users_repo.update(user_id, {"avatar": image_path})
        if not updated_user:
            raise HTTPException(status_code=500, detail="Error actualizando usuario")
    except Exception as e:
        # If database update fails, try to clean up the uploaded file
        try:
            await delete_file(image_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail=f"Error actualizando usuario: {str(e)}"
        )

    return {
        "id": updated_user.id,
        "avatar": updated_user.avatar,
        "avatar_url": generate_presigned_url(updated_user.avatar)
        if updated_user.avatar
        else None,
    }
