from clients.s3_client import get_s3_client
from core.config import settings
import time
import uuid
import os
import io
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

def generate_thumbnail(image_bytes: bytes, size: int = 100) -> bytes:
    """
    Generate a thumbnail from image bytes.

    Args:
        image_bytes: Original image bytes
        size: Thumbnail size (will create square thumbnail, e.g., 100x100)

    Returns:
        Thumbnail image bytes
    """
    if not PIL_AVAILABLE:
        return image_bytes

    try:
        # Open image
        img = Image.open(io.BytesIO(image_bytes))

        # Convert RGBA to RGB if needed (for JPEG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background

        # Create thumbnail maintaining aspect ratio
        img.thumbnail((size, size), Image.Resampling.LANCZOS)

        # Save to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        return output.read()
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return image_bytes


async def upload_file(file_content: bytes, folder: str, entity_id: str, extension: str, generate_thumbnails: bool = True) -> str:
    """
    Upload a file to an S3 bucket and return the relative path.

    Args:
        file_content: File content in bytes
        folder: S3 folder (e.g., "products", "businesses")
        entity_id: Entity ID for naming
        extension: File extension (e.g., ".jpg", ".png")
        generate_thumbnails: Whether to generate 100x100 thumbnail

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

        # Generate and upload thumbnail if requested and extension is an image
        if generate_thumbnails and extension.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            thumbnail_bytes = generate_thumbnail(file_content, size=100)

            # Upload thumbnail with _thumbnail suffix
            thumbnail_name = f"{folder}/{entity_id}_{timestamp}_thumbnail{extension}"
            s3_client.put_object(
                Bucket=settings.s3_bucket_name,
                Key=thumbnail_name,
                Body=thumbnail_bytes
            )

            # Invalidate cache for thumbnail
            thumbnail_cache_key = get_presigned_url_cache_key(thumbnail_name)
            invalidate_cache(thumbnail_cache_key)

            print(f"✓ Uploaded original and thumbnail: {object_name}")

    except Exception as e:
        print(f"Error uploading file to S3: {e}")
        raise e

    return object_name

async def delete_file(object_name: str):
    """Delete a file from an S3 bucket and its thumbnail if it exists."""
    if not object_name:
        return

    s3_client = get_s3_client()
    try:
        # Delete original file
        s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=object_name)

        # Invalidate cache for this presigned URL
        cache_key = get_presigned_url_cache_key(object_name)
        invalidate_cache(cache_key)

        # Try to delete thumbnail if it exists
        # Extract path and extension
        if '.' in object_name:
            base, ext = object_name.rsplit('.', 1)
            thumbnail_name = f"{base}_thumbnail.{ext}"

            try:
                s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=thumbnail_name)
                thumbnail_cache_key = get_presigned_url_cache_key(thumbnail_name)
                invalidate_cache(thumbnail_cache_key)
            except Exception:
                # Thumbnail might not exist, ignore
                pass

    except Exception as e:
        print(f"Error deleting file from S3: {e}")


def get_thumbnail_path(original_path: str) -> str:
    """
    Get the thumbnail path for an original image path.

    Args:
        original_path: Original S3 path (e.g., "products/123_456.jpg")

    Returns:
        Thumbnail path (e.g., "products/123_456_thumbnail.jpg")
    """
    if '.' in original_path:
        base, ext = original_path.rsplit('.', 1)
        return f"{base}_thumbnail.{ext}"
    return original_path
