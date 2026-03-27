"""Export GraphQL schema without initializing app dependencies."""
import sys
import os

# Mock settings to avoid validation errors
os.environ.setdefault('MONGODB_URL', 'mongodb://mock')
os.environ.setdefault('GEMINI_API_KEY', 'mock')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'mock')
os.environ.setdefault('AWS_DEFAULT_REGION', 'mock')
os.environ.setdefault('AWS_ENDPOINT_URL', 'mock')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'mock')
os.environ.setdefault('S3_BUCKET_NAME', 'mock')
os.environ.setdefault('JWT_SECRET_KEY', 'mock')
os.environ.setdefault('REDIS_URL', 'redis://mock')

from schema.schema import schema

print(schema.as_str())
