"""Redis cache utilities for data caching."""
import json
from typing import Optional, Any, List, Callable
from utils.rate_limit import redis_client


# =============================================================================
# Cache Configuration
# =============================================================================

# Default TTL values (in seconds)
TTL_DEFAULT = 300  # 5 minutes for products/branches/businesses
TTL_PRESIGNED_URL = 3000  # 50 minutes for S3 presigned URLs


# =============================================================================
# Generic Cache Functions
# =============================================================================

def get_cached(key: str) -> Optional[Any]:
    """
    Get a cached value from Redis.

    Args:
        key: Redis key to retrieve

    Returns:
        Cached value (deserialized from JSON) or None if not found
    """
    if redis_client is None:
        return None

    try:
        cached = redis_client.get(key)
        if cached:
            print(f"✓ Cache HIT: {key}")
            return json.loads(cached)
        print(f"✗ Cache MISS: {key}")
        return None
    except Exception as e:
        print(f"Cache get error for {key}: {e}")
        return None


def set_cached(key: str, value: Any, ttl: int = TTL_DEFAULT) -> bool:
    """
    Set a cached value in Redis.

    Args:
        key: Redis key to set
        value: Value to cache (will be serialized to JSON)
        ttl: Time-to-live in seconds (default: 5 minutes)

    Returns:
        True if successful, False otherwise
    """
    if redis_client is None:
        return False

    try:
        serialized = json.dumps(value, default=str)
        redis_client.setex(key, ttl, serialized)
        print(f"✓ Cache SET: {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        print(f"Cache set error for {key}: {e}")
        return False


def invalidate_cache(pattern: str) -> int:
    """
    Invalidate cache entries matching a pattern.

    Args:
        pattern: Redis key pattern (e.g., "products:*", "branch:123:*")

    Returns:
        Number of keys deleted
    """
    if redis_client is None:
        return 0

    try:
        keys = redis_client.keys(pattern)
        if keys:
            count = redis_client.delete(*keys)
            print(f"✓ Cache INVALIDATE: {pattern} ({count} keys)")
            return count
        return 0
    except Exception as e:
        print(f"Cache invalidate error for {pattern}: {e}")
        return 0


# =============================================================================
# Entity-Specific Cache Key Generators
# =============================================================================

def get_product_cache_key(suffix: str) -> str:
    """Generate cache key for products."""
    return f"cache:products:{suffix}"


def get_branch_cache_key(suffix: str) -> str:
    """Generate cache key for branches."""
    return f"cache:branches:{suffix}"


def get_business_cache_key(suffix: str) -> str:
    """Generate cache key for businesses."""
    return f"cache:businesses:{suffix}"


def get_presigned_url_cache_key(object_name: str) -> str:
    """Generate cache key for S3 presigned URLs."""
    return f"cache:presigned:{object_name}"


# =============================================================================
# Cache Invalidation Helpers
# =============================================================================

def invalidate_product_cache(branch_id: Optional[str] = None):
    """
    Invalidate product caches.

    Args:
        branch_id: If provided, only invalidate products for this branch
    """
    if branch_id:
        # Invalidate specific branch products
        invalidate_cache(get_product_cache_key(f"branch:{branch_id}"))
        invalidate_cache(get_product_cache_key(f"branch:{branch_id}:*"))
    else:
        # Invalidate all product caches
        invalidate_cache(get_product_cache_key("*"))


def invalidate_branch_cache(branch_id: Optional[str] = None, business_id: Optional[str] = None):
    """
    Invalidate branch caches.

    Args:
        branch_id: If provided, invalidate this specific branch
        business_id: If provided, invalidate branches for this business
    """
    if branch_id:
        invalidate_cache(get_branch_cache_key(f"id:{branch_id}"))
    if business_id:
        invalidate_cache(get_branch_cache_key(f"business:{business_id}"))
    if not branch_id and not business_id:
        invalidate_cache(get_branch_cache_key("*"))


def invalidate_business_cache(business_id: Optional[str] = None):
    """
    Invalidate business caches.

    Args:
        business_id: If provided, invalidate this specific business
    """
    if business_id:
        invalidate_cache(get_business_cache_key(f"id:{business_id}"))
    else:
        invalidate_cache(get_business_cache_key("*"))


# =============================================================================
# Cached Function Wrapper
# =============================================================================

async def with_cache(
    cache_key: str,
    fetch_fn: Callable,
    ttl: int = TTL_DEFAULT,
    serialize_fn: Optional[Callable] = None,
    deserialize_fn: Optional[Callable] = None
) -> Any:
    """
    Generic cache wrapper for async functions.

    Args:
        cache_key: Redis key for caching
        fetch_fn: Async function to call if cache miss (should return data)
        ttl: Time-to-live in seconds
        serialize_fn: Optional function to serialize result before caching
        deserialize_fn: Optional function to deserialize cached result

    Returns:
        Cached or freshly fetched data
    """
    # Try to get from cache
    cached = get_cached(cache_key)
    if cached is not None:
        if deserialize_fn:
            return deserialize_fn(cached)
        return cached

    # Fetch from source
    print(f"→ Fetching from source: {cache_key}")
    result = await fetch_fn()

    # Cache the result
    cache_data = serialize_fn(result) if serialize_fn else result
    set_cached(cache_key, cache_data, ttl)

    return result
