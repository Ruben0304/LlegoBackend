"""Redis cache utilities for data caching."""
import json
from typing import Optional, Any, List, Callable
from utils.rate_limit import redis_client
from core.config import settings


# =============================================================================
# Cache Configuration (from environment variables)
# =============================================================================

# TTL values are now controlled by environment variables
# settings.cache_all_on_startup: If True, cache everything permanently (no TTL)
# settings.cache_ttl: TTL for on-demand caching mode
# settings.cache_presigned_url_ttl: TTL for S3 presigned URLs

# Legacy constants for backward compatibility
TTL_DEFAULT = settings.cache_ttl
TTL_PRESIGNED_URL = settings.cache_presigned_url_ttl

# Flag to track if we're in "cache all" mode (set during warm-up)
_cache_all_mode = False


def is_cache_all_mode() -> bool:
    """Check if cache-all mode is enabled."""
    return settings.cache_all_on_startup


def get_effective_ttl(custom_ttl: Optional[int] = None) -> Optional[int]:
    """
    Get the effective TTL based on cache mode.
    
    In cache-all mode: Returns None (no expiration)
    In on-demand mode: Returns custom_ttl or settings.cache_ttl
    """
    if settings.cache_all_on_startup:
        return None  # No TTL in cache-all mode
    return custom_ttl if custom_ttl is not None else settings.cache_ttl


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


def set_cached(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """
    Set a cached value in Redis.

    Args:
        key: Redis key to set
        value: Value to cache (will be serialized to JSON)
        ttl: Time-to-live in seconds. If None and cache_all_on_startup=True, no expiration.
             If None and cache_all_on_startup=False, uses settings.cache_ttl.

    Returns:
        True if successful, False otherwise
    """
    if redis_client is None:
        return False

    try:
        serialized = json.dumps(value, default=str)
        effective_ttl = get_effective_ttl(ttl)
        
        if effective_ttl is None:
            # No TTL - permanent cache (until restart or manual invalidation)
            redis_client.set(key, serialized)
            print(f"✓ Cache SET: {key} (permanent)")
        else:
            redis_client.setex(key, effective_ttl, serialized)
            print(f"✓ Cache SET: {key} (TTL: {effective_ttl}s)")
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


def set_presigned_url_cached(key: str, value: Any) -> bool:
    """
    Set a cached presigned URL with TTL.
    
    Presigned URLs ALWAYS use TTL regardless of cache mode,
    because they have an expiration time from S3.
    """
    if redis_client is None:
        return False

    try:
        serialized = json.dumps(value, default=str)
        ttl = settings.cache_presigned_url_ttl
        redis_client.setex(key, ttl, serialized)
        print(f"✓ Cache SET (presigned): {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        print(f"Cache set error for {key}: {e}")
        return False


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
    ttl: Optional[int] = None,
    serialize_fn: Optional[Callable] = None,
    deserialize_fn: Optional[Callable] = None
) -> Any:
    """
    Generic cache wrapper for async functions.

    Args:
        cache_key: Redis key for caching
        fetch_fn: Async function to call if cache miss (should return data)
        ttl: Time-to-live in seconds (None uses default based on cache mode)
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


def should_cache_result(result_list: List[Any]) -> bool:
    """
    Determine if a result should be cached.
    
    In cache-all mode: Always cache everything
    In on-demand mode: Always cache (no size limit)

    Args:
        result_list: List of items to potentially cache

    Returns:
        True (always cache, no limits)
    """
    return True  # No limits - cache everything


# =============================================================================
# Cache Warm-up (for cache_all_on_startup mode)
# =============================================================================

async def warm_up_cache():
    """
    Pre-populate cache with all data at startup.

    This is automatically called when CACHE_ALL_ON_STARTUP=true.
    Data is cached permanently (no TTL) until server restart or manual invalidation.

    Usage:
        # In main.py, during startup:
        from utils.cache import warm_up_cache

        @app.on_event("startup")
        async def startup():
            await warm_up_cache()
    """
    if not settings.cache_all_on_startup:
        print("ℹ Cache warm-up skipped: CACHE_ALL_ON_STARTUP=false (using on-demand mode with TTL)")
        return

    if redis_client is None:
        print("⚠ Cache warm-up skipped: Redis not available")
        return

    try:
        from models import products_repo, branches_repo, businesses_repo

        print("🔥 Starting cache warm-up (CACHE_ALL_ON_STARTUP=true)...")
        print("   Mode: Permanent cache (no TTL)")

        # Warm up businesses
        businesses = await businesses_repo.get_all()
        print(f"   ✓ Warmed up {len(businesses)} businesses")

        # Warm up branches
        branches = await branches_repo.get_all()
        print(f"   ✓ Warmed up {len(branches)} branches")

        # Warm up products
        products = await products_repo.get_all()
        print(f"   ✓ Warmed up {len(products)} products")

        print(f"🔥 Cache warm-up complete! All data cached permanently.")

    except Exception as e:
        print(f"⚠ Cache warm-up failed: {e}")
