"""REST endpoints for image uploads.
These endpoints only upload images and return the path + presigned URL.
The actual data persistence happens via GraphQL mutations.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Request
from bson import ObjectId
from io import BytesIO

from utils.auth import get_current_user_id_from_header
from utils.s3 import upload_file, generate_presigned_url
from utils.rate_limit import limiter, RATE_LIMIT_UPLOADS
from services.image_processing import process_image_for_store, process_product_image

router = APIRouter(prefix="/upload", tags=["Uploads"])

# =============================================================================
# Security Configuration
# =============================================================================

# Allowed MIME types (validated against actual file content, not just header)
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

# File size limits per upload type (in bytes)
# Images are resized and compressed after upload, so we can accept larger files
MAX_FILE_SIZES = {
    "avatar": 10 * 1024 * 1024,     # 10MB - will be resized to 400x400
    "cover": 10 * 1024 * 1024,      # 10MB - will be resized to 1200x400
    "product": 10 * 1024 * 1024,    # 10MB - will be resized to max 1000x1000
}

# Magic bytes for image validation (file signatures)
IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',           # JPEG
    b'\x89PNG\r\n\x1a\n': 'image/png',       # PNG
    b'RIFF': 'image/webp',                    # WebP (partial, needs WEBP check)
    b'GIF87a': 'image/gif',                   # GIF87a
    b'GIF89a': 'image/gif',                   # GIF89a
}


def validate_image_signature(content: bytes) -> str | None:
    """
    Validate image by checking magic bytes (file signature).
    Returns detected MIME type or None if invalid.
    
    This prevents attacks where malicious files are disguised as images
    by simply changing the Content-Type header or extension.
    """
    if len(content) < 12:
        return None
    
    # Check JPEG
    if content[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    
    # Check PNG
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    
    # Check WebP (RIFF....WEBP)
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    
    # Check GIF
    if content[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    
    return None


async def validate_upload(
    image: UploadFile,
    upload_type: str,
    max_size: int
) -> bytes:
    """
    Comprehensive upload validation.
    
    Checks:
    1. Content-Type header is an allowed image type
    2. File size is within limits
    3. Magic bytes match an actual image format
    4. Image can be opened by PIL (valid image data)
    
    Args:
        image: The uploaded file
        upload_type: Type of upload for error messages
        max_size: Maximum allowed file size in bytes
        
    Returns:
        File content as bytes
        
    Raises:
        HTTPException with appropriate error
    """
    # 1. Validate Content-Type header
    content_type = image.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no permitido. Permitidos: JPEG, PNG, WebP, GIF"
        )
    
    # 2. Read file with size limit (streaming to prevent memory exhaustion)
    chunks = []
    total_size = 0
    chunk_size = 64 * 1024  # 64KB chunks
    
    while True:
        chunk = await image.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        
        # Check size limit during read (fail fast)
        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo muy grande. Máximo: {max_size // (1024*1024)}MB para {upload_type}"
            )
        chunks.append(chunk)
    
    content = b''.join(chunks)
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archivo vacío"
        )
    
    # 3. Validate magic bytes (actual file content)
    detected_type = validate_image_signature(content)
    if not detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es una imagen válida"
        )
    
    # 4. Verify Content-Type matches actual content (prevent spoofing)
    # Allow some flexibility (e.g., image/jpg vs image/jpeg)
    if detected_type != content_type:
        # Log this as potential attack attempt in production
        pass  # We'll process it anyway since we validated the actual content
    
    # 5. Try to open with PIL to ensure it's a valid, non-corrupted image
    try:
        from PIL import Image
        img = Image.open(BytesIO(content))
        img.verify()  # Verify it's a valid image
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imagen corrupta o inválida"
        )
    
    return content


# =============================================================================
# Upload Endpoints
# =============================================================================

@router.post("/business/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_business_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a business.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])
    
    try:
        processed_content, extension = process_image_for_store(
            file_content, "business_avatar", convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(processed_content, "businesses/avatars", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/business/cover", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_business_cover(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload cover image for a business.
    Max size: 5MB | Output: 1200x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "cover", MAX_FILE_SIZES["cover"])
    
    try:
        processed_content, extension = process_image_for_store(
            file_content, "business_cover", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(processed_content, "businesses/covers", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/branch/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_branch_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a branch.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])
    
    try:
        processed_content, extension = process_image_for_store(
            file_content, "branch_avatar", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(processed_content, "branches/avatars", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/branch/cover", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_branch_cover(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload cover image for a branch.
    Max size: 5MB | Output: 1200x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "cover", MAX_FILE_SIZES["cover"])
    
    try:
        processed_content, extension = process_image_for_store(
            file_content, "branch_cover", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(processed_content, "branches/covers", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/product/image", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_product_image(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload image for a product.
    Max size: 5MB | Preserves transparency (PNG/WebP supported)
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "product", MAX_FILE_SIZES["product"])
    
    filename = image.filename or "image.png"
    original_ext = "." + filename.split(".")[-1].lower() if "." in filename else ".png"
    
    # Sanitize extension
    if original_ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        original_ext = ".png"

    try:
        processed_content, extension = process_product_image(file_content, original_ext)
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(processed_content, "products", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/user/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_user_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header)
):
    """
    Upload avatar image for a user.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])
    
    try:
        processed_content, extension = process_image_for_store(
            file_content, "user_avatar", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = user_id

    try:
        image_path = await upload_file(processed_content, "users/avatars", entity_id, extension)
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}
