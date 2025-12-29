from clients.s3_client import get_s3_client
from core.config import settings
import time
import uuid
import os

def generate_presigned_url(object_name: str, expiration: int = 3600) -> str:
    """Generate a presigned URL to share an S3 object."""
    if not object_name:
        return ""
    
    # If the object_name is already a URL (e.g. from Google login), return it.
    if object_name.startswith("http"):
        return object_name

    s3_client = get_s3_client()
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.s3_bucket_name, 'Key': object_name},
            ExpiresIn=expiration
        )
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return ""
    return response

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
    except Exception as e:
        print(f"Error deleting file from S3: {e}")
