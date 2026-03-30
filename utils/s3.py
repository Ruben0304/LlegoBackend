import time
import io
from typing import Iterable, Optional, Union

from clients.s3_client import get_s3_client
from core.config import settings
from utils.cache import (
    get_cached,
    invalidate_cache,
    get_presigned_url_cache_key,
    set_cached,
    set_presigned_url_cached,
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠ PIL/Pillow not available. Thumbnails will not be generated.")


JPEG_QUALITY = 80
WEBP_QUALITY = 75
DEFAULT_THUMBNAIL_SIZE = 100
LEGACY_THUMBNAIL_VARIANT = "legacy_thumbnail"
PRODUCT_IMAGE_VARIANT_KEYS = ("muy_baja", "baja", "media", "alta")
AVATAR_IMAGE_VARIANT_KEYS = ("avatar_baja", "avatar_alta")
COVER_IMAGE_VARIANT_KEYS = ("cover_baja", "cover_alta")
ALL_DERIVED_IMAGE_VARIANT_KEYS = (
    LEGACY_THUMBNAIL_VARIANT,
    *PRODUCT_IMAGE_VARIANT_KEYS,
    *AVATAR_IMAGE_VARIANT_KEYS,
    *COVER_IMAGE_VARIANT_KEYS,
)
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
IMAGE_VARIANT_DEFINITIONS = {
    LEGACY_THUMBNAIL_VARIANT: {
        "suffix": "_thumbnail",
        "size": (100, 100),
        "extension": ".jpg",
        "quality": 85,
        "fit": False,
    },
    "muy_baja": {
        "suffix": "_thumbnail_muy_baja",
        "size": (200, 200),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "baja": {
        "suffix": "_thumbnail",
        "size": (720, 540),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "media": {
        "suffix": "_thumbnail_media",
        "size": (1080, 1350),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "alta": {
        "suffix": "_thumbnail_alta",
        "size": (1440, 1800),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "avatar_baja": {
        "suffix": "_avatar_baja",
        "size": (128, 128),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "avatar_alta": {
        "suffix": "_avatar_alta",
        "size": (400, 400),
        "extension": ".webp",
        "quality": 82,
        "fit": True,
    },
    "cover_baja": {
        "suffix": "_cover_baja",
        "size": (1280, 720),
        "extension": ".webp",
        "quality": WEBP_QUALITY,
        "fit": True,
    },
    "cover_alta": {
        "suffix": "_cover_alta",
        "size": (1920, 1080),
        "extension": ".webp",
        "quality": 82,
        "fit": True,
    },
}


def get_s3_exists_cache_key(object_name: str) -> str:
    """Generate cache key for S3 object existence checks."""
    return f"cache:s3:exists:{object_name}"

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


def _prepare_image_for_webp(img: "Image.Image") -> "Image.Image":
    """Normalize palette images before saving to WebP."""
    if img.mode == "P":
        return img.convert("RGBA")
    return img


def _resolve_variant_definition(variant: Optional[Union[str, int]]) -> dict:
    """Resolve product or legacy variant configuration."""
    if variant is None:
        return IMAGE_VARIANT_DEFINITIONS["baja"]

    if isinstance(variant, int):
        legacy_map = {
            100: "legacy_thumbnail",
            200: "muy_baja",
            500: "media",
            720: "baja",
            1000: "alta",
            1080: "media",
            1440: "alta",
        }
        variant = legacy_map.get(variant, "baja")

    return IMAGE_VARIANT_DEFINITIONS.get(str(variant), IMAGE_VARIANT_DEFINITIONS["baja"])


def generate_image_variant(
    image_bytes: bytes, variant: Union[str, int] = "baja"
) -> bytes:
    """
    Generate a resized image variant from image bytes.

    Args:
        image_bytes: Original image bytes
        variant: Variant key or legacy integer alias

    Returns:
        Image variant bytes
    """
    if not PIL_AVAILABLE:
        return image_bytes

    try:
        from PIL import ImageOps

        img = Image.open(io.BytesIO(image_bytes))
        definition = _resolve_variant_definition(variant)
        width, height = definition["size"]
        if definition["fit"]:
            img = ImageOps.fit(
                img,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        else:
            img.thumbnail((width, height), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        normalized_extension = definition["extension"].lower()
        quality = definition["quality"]

        if normalized_extension in (".jpg", ".jpeg"):
            img = _prepare_image_for_jpeg(img)
            img.save(output, format="JPEG", quality=quality, optimize=True)
        elif normalized_extension == ".png":
            img.save(output, format="PNG", optimize=True)
        elif normalized_extension == ".webp":
            img = _prepare_image_for_webp(img)
            img.save(output, format="WEBP", quality=quality, method=6)
        elif normalized_extension == ".gif":
            if img.mode not in ("P", "L"):
                img = img.convert("P", palette=Image.ADAPTIVE)
            img.save(output, format="GIF", optimize=True)
        else:
            img = _prepare_image_for_jpeg(img)
            img.save(output, format="JPEG", quality=quality, optimize=True)

        output.seek(0)
        return output.read()
    except Exception as e:
        print(f"Error generating image variant ({variant}): {e}")
        return image_bytes


def generate_thumbnail(image_bytes: bytes, size: int = DEFAULT_THUMBNAIL_SIZE) -> bytes:
    """Backward-compatible wrapper for the 100x100 thumbnail."""
    return generate_image_variant(image_bytes, variant=size)


def get_image_variant_path(
    original_path: str, variant: Union[str, int] = "baja"
) -> str:
    """
    Build the derived image path for a given size.

    Product variants use fixed named outputs in WebP.
    Legacy 100x100 thumbnail keeps `_thumbnail.jpg`.
    """
    if "." not in original_path:
        return original_path

    base, _ = original_path.rsplit(".", 1)
    definition = _resolve_variant_definition(variant)
    return f"{base}{definition['suffix']}{definition['extension']}"


def get_thumbnail_path(original_path: str) -> str:
    """Get the default low quality product thumbnail path for an original image."""
    return get_image_variant_path(original_path, "baja")


def get_image_variant_paths(
    original_path: str, variants: Optional[Iterable[Union[str, int]]] = None
) -> list[str]:
    """Get all derived image paths for the given original path."""
    resolved_variants = variants or ALL_DERIVED_IMAGE_VARIANT_KEYS
    return [get_image_variant_path(original_path, variant) for variant in resolved_variants]


def generate_image_variant_url(
    object_name: str, variant: Union[str, int], expiration: int = 3600
) -> str:
    """Generate a presigned URL for a specific derived image variant."""
    return generate_presigned_url(get_image_variant_path(object_name, variant), expiration)


def _s3_object_exists(object_name: str) -> bool:
    """Check whether an object exists in S3, with short cache for repeated lookups."""
    if not object_name:
        return False

    if object_name.startswith("http"):
        return True

    cache_key = get_s3_exists_cache_key(object_name)
    cached = get_cached(cache_key)
    if isinstance(cached, bool):
        return cached

    s3_client = get_s3_client()
    exists = False
    try:
        s3_client.head_object(Bucket=settings.s3_bucket_name, Key=object_name)
        exists = True
    except Exception:
        exists = False

    # Keep it short to avoid stale negatives after fresh uploads.
    set_cached(cache_key, exists, ttl=300)
    return exists


def generate_image_variant_url_with_fallback(
    object_name: str, variant: Union[str, int], expiration: int = 3600
) -> str:
    """
    Generate variant URL when available; otherwise return original URL.

    This keeps backward compatibility for historical images uploaded before
    variant generation was introduced for a specific media type.
    """
    if not object_name:
        return ""

    variant_path = get_image_variant_path(object_name, variant)
    if _s3_object_exists(variant_path):
        return generate_presigned_url(variant_path, expiration)
    return generate_presigned_url(object_name, expiration)


async def upload_file(
    file_content: bytes,
    folder: str,
    entity_id: str,
    extension: str,
    generate_thumbnails: bool = True,
    thumbnail_variants: Optional[Iterable[str]] = None,
) -> str:
    """
    Upload a file to an S3 bucket and return the relative path.

    Args:
        file_content: File content in bytes
        folder: S3 folder (e.g., "products", "businesses")
        entity_id: Entity ID for naming
        extension: File extension (e.g., ".jpg", ".png")
        generate_thumbnails: Whether to generate derived image variants
        thumbnail_variants: Variant keys for derived images

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
        invalidate_cache(get_s3_exists_cache_key(object_name))

        if generate_thumbnails and extension.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            variant_keys = list(thumbnail_variants or [LEGACY_THUMBNAIL_VARIANT])

            for variant in variant_keys:
                variant_bytes = generate_image_variant(file_content, variant=variant)
                variant_name = get_image_variant_path(object_name, variant)
                s3_client.put_object(
                    Bucket=settings.s3_bucket_name,
                    Key=variant_name,
                    Body=variant_bytes
                )

                variant_cache_key = get_presigned_url_cache_key(variant_name)
                invalidate_cache(variant_cache_key)
                invalidate_cache(get_s3_exists_cache_key(variant_name))

            print(
                f"✓ Uploaded original and {len(variant_keys)} derived image(s): {object_name}"
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
        invalidate_cache(get_s3_exists_cache_key(object_name))

        for variant_name in get_image_variant_paths(object_name):
            try:
                s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=variant_name)
                variant_cache_key = get_presigned_url_cache_key(variant_name)
                invalidate_cache(variant_cache_key)
                invalidate_cache(get_s3_exists_cache_key(variant_name))
            except Exception:
                pass

    except Exception as e:
        print(f"Error deleting file from S3: {e}")
