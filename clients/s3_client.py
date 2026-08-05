import boto3
from botocore.config import Config
from core.config import settings

_s3_client = None


def get_s3_client():
    """Return a cached S3 client (singleton — boto3 clients are thread-safe for signing)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_default_region,
            config=Config(signature_version='s3v4')
        )
    return _s3_client
