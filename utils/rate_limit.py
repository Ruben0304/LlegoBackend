"""Rate limiting configuration using Redis."""
import redis
import threading
import time
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# In-memory fallback counters used when Redis is unavailable.
# Keys encode the minute window so old entries never produce false positives.
_memory_fallback: dict[str, int] = {}
_memory_lock = threading.Lock()

from core.config import settings
from utils.auth import decode_access_token


# =============================================================================
# Rate Limit Definitions (requests per minute)
# =============================================================================

RATE_LIMITS = {
    "auth": 5,           # Login/register - by IP
    "graphql": 40,       # General GraphQL queries
    "graphql_anon": 30,  # GraphQL without auth
    "uploads": 6,        # File uploads
    "search": 10,        # Vector search (expensive)
    "ai": 2,             # AI Assistant (very expensive)
}

# For slowapi decorators (REST endpoints)
RATE_LIMIT_AUTH = "5/minute"
RATE_LIMIT_UPLOADS = "6/minute"


# =============================================================================
# Redis Client
# =============================================================================

redis_client: Optional[redis.Redis] = None

def init_redis() -> bool:
    """Initialize Redis connection. Returns True if successful."""
    global redis_client
    try:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
        print(f"✓ Rate limiter connected to Redis")
        return True
    except Exception as e:
        print(f"⚠ Redis not available: {e}")
        redis_client = None
        return False

# Initialize on module load
_redis_available = init_redis()


def get_redis_status() -> dict:
    """Get Redis connection status for diagnostics."""
    global redis_client
    if redis_client is None:
        return {"connected": False, "error": "Not initialized"}
    try:
        redis_client.ping()
        info = redis_client.info("server")
        return {
            "connected": True,
            "version": info.get("redis_version"),
            "url": settings.redis_url[:30] + "..." if len(settings.redis_url) > 30 else settings.redis_url
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


# =============================================================================
# GraphQL Rate Limiting
# =============================================================================

def _get_rate_limit_key(identifier: str, limit_type: str) -> str:
    """Generate Redis key for rate limiting."""
    minute = int(time.time() // 60)
    return f"ratelimit:{limit_type}:{identifier}:{minute}"


def check_rate_limit(identifier: str, limit_type: str) -> tuple[bool, int]:
    """
    Check if request is within rate limit.
    
    Args:
        identifier: User ID or IP address
        limit_type: One of 'graphql', 'search', 'ai', etc.
        
    Returns:
        Tuple of (allowed: bool, current_count: int)
    """
    global redis_client

    limit = RATE_LIMITS.get(limit_type, 30)
    key = _get_rate_limit_key(identifier, limit_type)

    if redis_client is None:
        return _check_memory_fallback(key, limit)
    
    try:
        current = redis_client.get(key)
        current_count = int(current) if current else 0

        if current_count >= limit:
            return False, current_count

        # Increment counter
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)  # Expire after 1 minute
        pipe.execute()

        return True, current_count + 1
    except Exception as e:
        print(f"Rate limit check error: {e}")
        return _check_memory_fallback(key, limit)


def _check_memory_fallback(key: str, limit: int) -> tuple[bool, int]:
    """
    In-memory rate limit fallback used when Redis is unavailable or errors.

    Keys already encode the current minute window (via _get_rate_limit_key),
    so stale entries from previous minutes are harmless — they live under
    different keys and are purged lazily on each call.
    """
    current_minute = int(time.time() // 60)

    with _memory_lock:
        # Purge keys that belong to a previous minute window
        stale = [k for k in _memory_fallback
                 if not k.endswith(f":{current_minute}")]
        for k in stale:
            del _memory_fallback[k]

        count = _memory_fallback.get(key, 0)
        if count >= limit:
            return False, count
        _memory_fallback[key] = count + 1
        return True, count + 1


def get_identifier_from_context(info) -> str:
    """Extract user ID or IP from Strawberry context."""
    context = info.context
    
    # Try user_id first (authenticated)
    user_id = context.get("user_id")
    if user_id:
        return f"user:{user_id}"
    
    # Fallback to IP
    request = context.get("request")
    if request:
        # Get real IP (considering proxies)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"ip:{ip}"
    
    return "ip:unknown"


def rate_limit_graphql(info, limit_type: str = "graphql"):
    """
    Check rate limit for GraphQL operations.
    Raises Exception if limit exceeded.
    
    Usage in resolver:
        rate_limit_graphql(info, "search")
    """
    identifier = get_identifier_from_context(info)
    allowed, count = check_rate_limit(identifier, limit_type)
    
    if not allowed:
        limit = RATE_LIMITS.get(limit_type, 30)
        raise Exception(f"Rate limit exceeded ({limit}/min). Try again later.")


# =============================================================================
# REST Rate Limiting (slowapi)
# =============================================================================

def get_user_or_ip(request: Request) -> str:
    """Get rate limit key: user_id if authenticated, IP otherwise."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if payload and "user_id" in payload:
            return f"user:{payload['user_id']}"
    
    return f"ip:{get_remote_address(request)}"


# Create limiter for REST endpoints
limiter = Limiter(
    key_func=get_user_or_ip,
    storage_uri=settings.redis_url if _redis_available else None,
    default_limits=["20/minute"]
)


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
