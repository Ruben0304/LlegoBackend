"""Rate limiting configuration using slowapi with Redis backend."""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import redis

from core.config import settings
from utils.auth import decode_access_token


def get_user_or_ip(request: Request) -> str:
    """
    Get rate limit key: user_id if authenticated, IP otherwise.
    This ensures authenticated users get their own limit bucket.
    """
    # Try to get user from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if payload and "user_id" in payload:
            return f"user:{payload['user_id']}"
    
    # Fallback to IP
    return f"ip:{get_remote_address(request)}"


def get_ip_only(request: Request) -> str:
    """Get IP address for rate limiting (used for auth endpoints)."""
    return f"ip:{get_remote_address(request)}"


# Initialize Redis storage for rate limiting
try:
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    redis_client.ping()  # Test connection
    storage_uri = settings.redis_url
    print(f"✓ Rate limiter connected to Redis")
except Exception as e:
    print(f"⚠ Redis not available, using in-memory rate limiting: {e}")
    storage_uri = None

# Create limiter with Redis backend (falls back to memory if Redis unavailable)
limiter = Limiter(
    key_func=get_user_or_ip,
    storage_uri=storage_uri,
    default_limits=["20/minute"]  # Default for all endpoints
)


# =============================================================================
# Rate Limit Definitions
# =============================================================================

# Auth endpoints - by IP to prevent brute force
RATE_LIMIT_AUTH = "5/minute"

# General GraphQL - authenticated users
RATE_LIMIT_GRAPHQL = "20/minute"

# GraphQL without auth - stricter to prevent scraping
RATE_LIMIT_GRAPHQL_ANON = "30/minute"

# File uploads
RATE_LIMIT_UPLOADS = "6/minute"

# Vector search (expensive: Gemini + Qdrant)
RATE_LIMIT_SEARCH = "10/minute"

# AI Assistant (very expensive: Gemini API)
RATE_LIMIT_AI = "2/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
            "retry_after": exc.detail
        }
    )
