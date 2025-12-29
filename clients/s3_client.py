import boto3
from botocore.config import Config
from core.config import settings

def get_s3_client():
    """Create and return an S3 client."""
    return boto3.client(
        's3',
        endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_default_region,
        config=Config(signature_version='s3v4')
    )
