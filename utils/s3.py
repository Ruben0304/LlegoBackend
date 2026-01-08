from clients.s3_client import get_s3_client
from core.config import settings
import time
import uuid
import os
from utils.cache import (
    get_cached, invalidate_cache,
    get_presigned_url_cache_key, set_presigned_url_cached
)

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

async def upload_file(file_content: bytes, folder: str, entity_id: str, extension: str) -> str:
    """Upload a file to an S3 bucket and return the relative path."""
    timestamp = int(time.time())
    object_name = f"{folder}/{entity_id}_{timestamp}{extension}"

    s3_client = get_s3_client()
    try:
        # Running sync s3 call in async wrapper if needed, or just directly
        # Boto3 client is synchronous. For high load, consider aiobotocore.
        # For now, simplistic usage.
        s3_client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_name,
            Body=file_content
        )

        # Invalidate cache for this object (if it existed before)
        cache_key = get_presigned_url_cache_key(object_name)
        invalidate_cache(cache_key)

    except Exception as e:
        print(f"Error uploading file to S3: {e}")
        raise e

    return object_name

async def delete_file(object_name: str):
    """Delete a file from an S3 bucket."""
    if not object_name:
        return

    s3_client = get_s3_client()
    try:
        s3_client.delete_object(Bucket=settings.s3_bucket_name, Key=object_name)

        # Invalidate cache for this presigned URL
        cache_key = get_presigned_url_cache_key(object_name)
        invalidate_cache(cache_key)

    except Exception as e:
        print(f"Error deleting file from S3: {e}")
