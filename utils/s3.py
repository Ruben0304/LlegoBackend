import time
import io
from typing import Iterable, Optional

from clients.s3_client import get_s3_client
from core.config import settings
from utils.cache import (
    get_cached, invalidate_cache,
    get_presigned_url_cache_key, set_presigned_url_cached
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠ PIL/Pillow not available. Thumbnails will not be generated.")


JPEG_QUALITY = 85
DEFAULT_THUMBNAIL_SIZE = 100
PRODUCT_IMAGE_VARIANT_SIZES = (100, 500, 1000)
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

def generate_presigned_url(object_name: str, expiration: int = 3600) -> str:
    """
    Generate a presigned URL to share an S3 object with caching.

    URLs are cached with a 50-minute TTL (since they expire in 60 minutes)
    to avoid regenerating them on every request.
    """
    if not object_name:
        return ""

    # If the object_name is already a URL (e.g. from Google login), return it.
    if object_name.startswith("http"):
        return object_name

    # Try to get from cache
    cache_key = get_presigned_url_cache_key(object_name)
    cached_url = get_cached(cache_key)

    if cached_url is not None:
        return cached_url

    # Generate new presigned URL
    s3_client = get_s3_client()
    try:
        print(f"→ Generating presigned URL for {object_name}")
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.s3_bucket_name, 'Key': object_name},
            ExpiresIn=expiration
        )

        # Cache the URL (always with TTL since presigned URLs expire)
        set_presigned_url_cached(cache_key, response)

        return response
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return ""

def _prepare_image_for_jpeg(img: "Image.Image") -> "Image.Image":
    """Flatten transparency to white before saving as JPEG."""
    if img.mode == "P":
        img = img.convert("RGBA")

    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background

    if img.mode != "RGB":
        return img.convert("RGB")

    return img


def generate_image_variant(
    image_bytes: bytes, size: int = DEFAULT_THUMBNAIL_SIZE, output_extension: str = ".jpg"
) -> bytes:
    """
    Generate a resized image variant from image bytes.

    Args:
        image_bytes: Original image bytes
        size: Maximum size for width/height while preserving aspect ratio
        output_extension: Output extension/format

    Returns:
        Image variant bytes
    """
    if not PIL_AVAILABLE:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((size, size), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        normalized_extension = output_extension.lower()

        if normalized_extension in (".jpg", ".jpeg"):
            img = _prepare_image_for_jpeg(img)
            img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        elif normalized_extension == ".png":
            img.save(output, format="PNG", optimize=True)
        elif normalized_extension == ".webp":
            if img.mode == "P":
                img = img.convert("RGBA")
            img.save(output, format="WEBP", quality=JPEG_QUALITY)
        elif normalized_extension == ".gif":
            if img.mode not in ("P", "L"):
                img = img.convert("P", palette=Image.ADAPTIVE)
            img.save(output, format="GIF", optimize=True)
        else:
            img = _prepare_image_for_jpeg(img)
            img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)

        output.seek(0)
        return output.read()
    except Exception as e:
        print(f"Error generating image variant ({size}px): {e}")
        return image_bytes


def generate_thumbnail(image_bytes: bytes, size: int = DEFAULT_THUMBNAIL_SIZE) -> bytes:
    """Backward-compatible wrapper for the 100x100 thumbnail."""
    return generate_image_variant(image_bytes, size=size, output_extension=".jpg")


def get_image_variant_path(original_path: str, size: int = DEFAULT_THUMBNAIL_SIZE) -> str:
    """
    Build the derived image path for a given size.

    100x100 keeps the legacy `_thumbnail` suffix for backwards compatibility.
    Other sizes use `_thumbnail_{size}`.
    """
    if "." not in original_path:
        return original_path

    base, ext = original_path.rsplit(".", 1)
    suffix = "_thumbnail" if size == DEFAULT_THUMBNAIL_SIZE else f"_thumbnail_{size}"
    return f"{base}{suffix}.{ext}"


def get_thumbnail_path(original_path: str) -> str:
    """Get the legacy 100x100 thumbnail path for an original image."""
    return get_image_variant_path(original_path, DEFAULT_THUMBNAIL_SIZE)


def get_image_variant_paths(
    original_path: str, sizes: Optional[Iterable[int]] = None
) -> list[str]:
    """Get all derived image paths for the given original path."""
    resolved_sizes = sizes or PRODUCT_IMAGE_VARIANT_SIZES
    return [get_image_variant_path(original_path, size) for size in resolved_sizes]


def generate_image_variant_url(
    object_name: str, size: int, expiration: int = 3600
) -> str:
    """Generate a presigned URL for a specific derived image variant."""
    return generate_presigned_url(get_image_variant_path(object_name, size), expiration)


async def upload_file(
    file_content: bytes,
    folder: str,
    entity_id: str,
    extension: str,
    generate_thumbnails: bool = True,
    thumbnail_sizes: Optional[Iterable[int]] = None,
) -> str:
    """
    Upload a file to an S3 bucket and return the relative path.

    Args:
        file_content: File content in bytes
        folder: S3 folder (e.g., "products", "businesses")
        entity_id: Entity ID for naming
        extension: File extension (e.g., ".jpg", ".png")
        generate_thumbnails: Whether to generate derived image variants
        thumbnail_sizes: Sizes for derived variants (defaults to [100])

    Returns:
        Relative path to the uploaded file
    """
    timestamp = int(time.time())
    object_name = f"{folder}/{entity_id}_{timestamp}{extension}"

    s3_client = get_s3_client()
    try:
        # Upload original image
        s3_client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_name,
            Body=file_content
        )

        # Invalidate cache for this object (if it existed before)
        cache_key = get_presigned_url_cache_key(object_name)
        invalidate_cache(cache_key)

        if generate_thumbnails and extension.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            variant_sizes = list(thumbnail_sizes or [DEFAULT_THUMBNAIL_SIZE])

            for size in variant_sizes:
                variant_bytes = generate_image_variant(
                    file_content, size=size, output_extension=extension
                )
                variant_name = get_image_variant_path(object_name, size)
                s3_client.put_object(
                    Bucket=settings.s3_bucket_name,
                    Key=variant_name,
                    Body=variant_bytes
                )

                variant_cache_key = get_presigned_url_cache_key(variant_name)
                invalidate_cache(variant_cache_key)

            print(
                f"✓ Uploaded original and {len(variant_sizes)} derived image(s): {object_name}"
            )

    except Exception as e:
        print(f"Error uploading file to S3: {e}")
        raise e

    return object_name

async def delete_file(object_name: str):
    """Delete a file from an S3 bucket and its derived variants if they exist."""
    if not object_name:
        return

    s3_client = get_s3_client()
    try:
        # Delete original file
        s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=object_name)

        # Invalidate cache for this presigned URL
        cache_key = get_presigned_url_cache_key(object_name)
        invalidate_cache(cache_key)

        for variant_name in get_image_variant_paths(object_name):
            try:
                s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=variant_name)
                variant_cache_key = get_presigned_url_cache_key(variant_name)
                invalidate_cache(variant_cache_key)
            except Exception:
                pass

    except Exception as e:
        print(f"Error deleting file from S3: {e}")
