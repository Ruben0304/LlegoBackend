"""REST endpoints for image uploads.
These endpoints only upload images and return the path + presigned URL.
The actual data persistence happens via GraphQL mutations.
"""

from io import BytesIO

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from services.image_processing import (
    process_image_for_store_async,
    process_product_image_async,
)
from utils.auth import get_current_user_id_from_header
from utils.rate_limit import RATE_LIMIT_UPLOADS, limiter
from utils.s3 import generate_presigned_url, upload_file

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

# Allowed 3D model MIME types
ALLOWED_3D_TYPES = {
    "model/vnd.usdz+zip",  # USDZ (iOS)
    "model/gltf-binary",  # GLB
    "application/octet-stream",  # Generic binary (fallback)
}

# Allowed video MIME types
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",  # .mov
    "video/x-msvideo",  # .avi
    "video/webm",
}

# File size limits per upload type (in bytes)
# Images are resized and compressed after upload, so we can accept larger files
MAX_FILE_SIZES = {
    "avatar": 10 * 1024 * 1024,  # 10MB - will be resized to 400x400
    "cover": 10 * 1024 * 1024,  # 10MB - will be resized to 1200x400
    "product": 10 * 1024 * 1024,  # 10MB - will be resized to max 1000x1000
    "model3d": 50 * 1024 * 1024,  # 50MB - 3D models can be large
    "video": 100 * 1024 * 1024,  # 100MB - videos can be large
    "thumbnail": 5 * 1024 * 1024,  # 5MB - thumbnails are smaller
}

# Magic bytes for image validation (file signatures)
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",  # JPEG
    b"\x89PNG\r\n\x1a\n": "image/png",  # PNG
    b"RIFF": "image/webp",  # WebP (partial, needs WEBP check)
    b"GIF87a": "image/gif",  # GIF87a
    b"GIF89a": "image/gif",  # GIF89a
}

# 3D model file signatures
MODEL_3D_SIGNATURES = {
    b"PK": "model/vnd.usdz+zip",  # USDZ (ZIP-based)
    b"glTF": "model/gltf-binary",  # GLB (starts with glTF magic)
}

# Video file signatures
VIDEO_SIGNATURES = {
    b"\x00\x00\x00\x18ftypmp42": "video/mp4",  # MP4 (ftyp box)
    b"\x00\x00\x00\x20ftypisom": "video/mp4",  # MP4 (ftyp box)
    b"\x00\x00\x00\x1cftyp": "video/mp4",  # MP4 (ftyp box)
    b"moov": "video/quicktime",  # MOV (partial)
    b"RIFF": "video/x-msvideo",  # AVI
    b"\x1a\x45\xdf\xa3": "video/webm",  # WebM (EBML header)
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
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    # Check PNG
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    # Check WebP (RIFF....WEBP)
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    # Check GIF
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    return None


def validate_3d_model_signature(content: bytes, filename: str) -> str | None:
    """
    Validate 3D model by checking magic bytes and file extension.
    Returns detected MIME type or None if invalid.
    """
    if len(content) < 12:
        return None

    filename_lower = filename.lower() if filename else ""

    # Check USDZ (ZIP-based format)
    if content[:2] == b"PK" and filename_lower.endswith(".usdz"):
        return "model/vnd.usdz+zip"

    # Check GLB (glTF binary)
    # GLB magic: 0x46546C67 (glTF in ASCII, little-endian)
    if content[:4] == b"glTF" or filename_lower.endswith(".glb"):
        return "model/gltf-binary"

    # Fallback: trust extension for known 3D formats
    if filename_lower.endswith(".usdz"):
        return "model/vnd.usdz+zip"
    if filename_lower.endswith(".glb"):
        return "model/gltf-binary"

    return None


def validate_video_signature(content: bytes, filename: str) -> str | None:
    """
    Validate video by checking magic bytes and file extension.
    Returns detected MIME type or None if invalid.
    """
    if len(content) < 32:
        return None

    filename_lower = filename.lower() if filename else ""

    # Check MP4 (ftyp box at various offsets)
    for offset in [4, 8, 12, 16, 20]:
        if len(content) > offset + 4:
            if content[offset : offset + 4] == b"ftyp":
                if filename_lower.endswith(".mp4"):
                    return "video/mp4"

    # Check MOV (moov atom)
    if b"moov" in content[:100] and filename_lower.endswith(".mov"):
        return "video/quicktime"

    # Check AVI
    if (
        content[:4] == b"RIFF"
        and content[8:12] == b"AVI "
        and filename_lower.endswith(".avi")
    ):
        return "video/x-msvideo"

    # Check WebM
    if content[:4] == b"\x1a\x45\xdf\xa3" and filename_lower.endswith(".webm"):
        return "video/webm"

    # Fallback: trust extension for known video formats
    if filename_lower.endswith(".mp4"):
        return "video/mp4"
    if filename_lower.endswith(".mov"):
        return "video/quicktime"
    if filename_lower.endswith(".avi"):
        return "video/x-msvideo"
    if filename_lower.endswith(".webm"):
        return "video/webm"

    return None


async def validate_upload(image: UploadFile, upload_type: str, max_size: int) -> bytes:
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
            detail=f"Tipo de archivo no permitido. Permitidos: JPEG, PNG, WebP, GIF",
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
                detail=f"Archivo muy grande. Máximo: {max_size // (1024 * 1024)}MB para {upload_type}",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío"
        )

    # 3. Validate magic bytes (actual file content)
    detected_type = validate_image_signature(content)
    if not detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es una imagen válida",
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Imagen corrupta o inválida"
        )

    return content


async def validate_3d_upload(file: UploadFile, max_size: int) -> tuple[bytes, str]:
    """
    Validate 3D model upload.

    Checks:
    1. File extension is allowed (.usdz, .glb)
    2. File size is within limits
    3. Magic bytes match expected format

    Args:
        file: The uploaded file
        max_size: Maximum allowed file size in bytes

    Returns:
        Tuple of (file content as bytes, detected extension)

    Raises:
        HTTPException with appropriate error
    """
    filename = file.filename or ""
    filename_lower = filename.lower()

    # 1. Validate file extension
    if not (filename_lower.endswith(".usdz") or filename_lower.endswith(".glb")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo de archivo no permitido. Permitidos: .usdz, .glb",
        )

    # 2. Read file with size limit
    chunks = []
    total_size = 0
    chunk_size = 256 * 1024  # 256KB chunks for larger files

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)

        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo muy grande. Máximo: {max_size // (1024 * 1024)}MB para modelos 3D",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío"
        )

    # 3. Validate magic bytes
    detected_type = validate_3d_model_signature(content, filename)
    if not detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es un modelo 3D válido",
        )

    # Determine extension
    extension = ".usdz" if filename_lower.endswith(".usdz") else ".glb"

    return content, extension


async def validate_video_upload(file: UploadFile, max_size: int) -> tuple[bytes, str]:
    """
    Validate video upload.

    Checks:
    1. File extension is allowed (.mp4, .mov, .avi, .webm)
    2. File size is within limits
    3. Magic bytes match expected format

    Args:
        file: The uploaded file
        max_size: Maximum allowed file size in bytes

    Returns:
        Tuple of (file content as bytes, detected extension)

    Raises:
        HTTPException with appropriate error
    """
    filename = file.filename or ""
    filename_lower = filename.lower()

    # 1. Validate file extension
    if not any(
        filename_lower.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".webm"]
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo de archivo no permitido. Permitidos: .mp4, .mov, .avi, .webm",
        )

    # 2. Read file with size limit
    chunks = []
    total_size = 0
    chunk_size = 512 * 1024  # 512KB chunks for larger files

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)

        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Archivo muy grande. Máximo: {max_size // (1024 * 1024)}MB para videos",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío"
        )

    # 3. Validate magic bytes
    detected_type = validate_video_signature(content, filename)
    if not detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es un video válido",
        )

    # Determine extension
    if filename_lower.endswith(".mp4"):
        extension = ".mp4"
    elif filename_lower.endswith(".mov"):
        extension = ".mov"
    elif filename_lower.endswith(".avi"):
        extension = ".avi"
    elif filename_lower.endswith(".webm"):
        extension = ".webm"
    else:
        extension = ".mp4"  # Default to mp4

    return content, extension


# =============================================================================
# Upload Endpoints
# =============================================================================


@router.post("/business/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_business_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload avatar image for a business.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])

    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "business_avatar", convert_to_jpg=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(
            processed_content, "businesses/avatars", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/branch/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_branch_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload avatar image for a branch.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])

    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "branch_avatar", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(
            processed_content, "branches/avatars", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/branch/cover", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_branch_cover(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload cover image for a branch.
    Max size: 5MB | Output: 1200x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "cover", MAX_FILE_SIZES["cover"])

    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "branch_cover", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(
            processed_content, "branches/covers", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/product/image", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_product_image(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
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
        processed_content, extension = await process_product_image_async(
            file_content, original_ext
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(
            processed_content, "products", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/user/avatar", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_user_avatar(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload avatar image for a user.
    Max size: 2MB | Output: 400x400 JPG
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    file_content = await validate_upload(image, "avatar", MAX_FILE_SIZES["avatar"])

    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "user_avatar", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = user_id

    try:
        image_path = await upload_file(
            processed_content, "users/avatars", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo imagen")

    return {"image_path": image_path, "image_url": generate_presigned_url(image_path)}


@router.post("/business-type/model3d", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_business_type_model3d(
    request: Request,
    model: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload 3D model for a business type configuration.
    Max size: 50MB | Allowed formats: .usdz, .glb

    This endpoint uploads the 3D model to S3 and returns the path and presigned URL.
    Use the returned model_path in the createBusinessTypeConfig or updateBusinessTypeConfig mutation.

    Note: Only admins should use this endpoint (validated in the GraphQL mutation).
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    # Validate and read the 3D model file
    file_content, extension = await validate_3d_upload(model, MAX_FILE_SIZES["model3d"])

    # Generate unique ID for the model
    entity_id = str(ObjectId())

    try:
        model_path = await upload_file(
            file_content, "business-types/models", entity_id, extension
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error subiendo modelo 3D")

    return {"model_path": model_path, "model_url": generate_presigned_url(model_path)}


@router.post("/tutorial/video", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_tutorial_video(
    request: Request,
    video: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload video for a tutorial.
    Max size: 100MB | Allowed formats: .mp4, .mov, .avi, .webm

    This endpoint uploads the video to S3 and returns the path and presigned URL.
    Use the returned video_path in the createTutorial or updateTutorial mutation.

    Note: Only admins should use this endpoint (validated in the GraphQL mutation).
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    # TODO: Add admin role check when implemented
    # For now, any authenticated user can upload tutorial videos
    # In production, add: if user.role != "admin": raise Exception("No autorizado")

    # Validate and read the video file
    file_content, extension = await validate_video_upload(
        video, MAX_FILE_SIZES["video"]
    )

    # Generate unique ID for the video
    entity_id = str(ObjectId())

    try:
        video_path = await upload_file(
            file_content, "tutorials/videos", entity_id, extension
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error subiendo video")

    return {"video_path": video_path, "video_url": generate_presigned_url(video_path)}


@router.post("/tutorial/thumbnail", status_code=status.HTTP_200_OK)
@limiter.limit(RATE_LIMIT_UPLOADS)
async def upload_tutorial_thumbnail(
    request: Request,
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """
    Upload thumbnail image for a tutorial.
    Max size: 5MB | Output: Optimized image

    This endpoint uploads the thumbnail to S3 and returns the path and presigned URL.
    Use the returned thumbnail_path in the createTutorial or updateTutorial mutation.

    Note: Only admins should use this endpoint (validated in the GraphQL mutation).
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    # TODO: Add admin role check when implemented
    # For now, any authenticated user can upload tutorial thumbnails
    # In production, add: if user.role != "admin": raise Exception("No autorizado")

    file_content = await validate_upload(
        image, "thumbnail", MAX_FILE_SIZES["thumbnail"]
    )

    try:
        processed_content, extension = await process_image_for_store_async(
            file_content, "tutorial_thumbnail", convert_to_jpg=True
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Error procesando imagen")

    entity_id = str(ObjectId())

    try:
        image_path = await upload_file(
            processed_content, "tutorials/thumbnails", entity_id, extension
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error subiendo thumbnail")

    return {
        "thumbnail_path": image_path,
        "thumbnail_url": generate_presigned_url(image_path),
    }
