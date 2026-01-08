"""DataLoaders for efficient batch loading and avoiding N+1 queries."""
from collections import defaultdict
from typing import List, Optional
from strawberry.dataloader import DataLoader

from models import products_repo, branches_repo, businesses_repo, Product, Branch, Business
from utils.cache import (
    get_cached, set_cached,
    get_product_cache_key, get_branch_cache_key, get_business_cache_key,
    TTL_DEFAULT
)


async def load_products_for_branches(branch_ids: List[str]) -> List[List]:
    """
    Batch load products for multiple branches in a single query.
    Uses cache to avoid repeated queries.
    """
    # Try to get cached products for each branch
    products_by_branch = defaultdict(list)
    uncached_branch_ids = []

    for branch_id in branch_ids:
        cache_key = get_product_cache_key(f"branch:{branch_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            # Deserialize cached products
            products_by_branch[branch_id] = [Product(**p) for p in cached]
        else:
            uncached_branch_ids.append(branch_id)

    # Fetch uncached branches from database
    if uncached_branch_ids:
        print(f"→ Fetching products for {len(uncached_branch_ids)} branches from database")
        all_products = await products_repo.get_by_branch_ids(uncached_branch_ids)

        # Group by branch and cache
        uncached_products_by_branch = defaultdict(list)
        for product in all_products:
            uncached_products_by_branch[product.branchId].append(product)

        for branch_id in uncached_branch_ids:
            branch_products = uncached_products_by_branch.get(branch_id, [])
            products_by_branch[branch_id] = branch_products

            # Cache the products for this branch
            cache_key = get_product_cache_key(f"branch:{branch_id}")
            serialized = [p.model_dump() for p in branch_products]
            set_cached(cache_key, serialized, TTL_DEFAULT)

    return [products_by_branch.get(bid, []) for bid in branch_ids]


async def load_branches(branch_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load branches by IDs in a single query.
    Uses cache to avoid repeated queries.
    """
    # Try to get cached branches
    branch_map = {}
    uncached_ids = []

    for branch_id in branch_ids:
        cache_key = get_branch_cache_key(f"id:{branch_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            # Deserialize cached branch
            branch_map[branch_id] = Branch(**cached)
        else:
            uncached_ids.append(branch_id)

    # Fetch uncached branches from database
    if uncached_ids:
        print(f"→ Fetching {len(uncached_ids)} branches from database")
        branches = await branches_repo.get_by_ids(uncached_ids)

        for branch in branches:
            branch_map[branch.id] = branch

            # Cache the branch
            cache_key = get_branch_cache_key(f"id:{branch.id}")
            set_cached(cache_key, branch.model_dump(), TTL_DEFAULT)

    return [branch_map.get(bid) for bid in branch_ids]


async def load_businesses(business_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load businesses by IDs in a single query.
    Uses cache to avoid repeated queries.
    """
    # Try to get cached businesses
    business_map = {}
    uncached_ids = []

    for business_id in business_ids:
        cache_key = get_business_cache_key(f"id:{business_id}")
        cached = get_cached(cache_key)

        if cached is not None:
            # Deserialize cached business
            business_map[business_id] = Business(**cached)
        else:
            uncached_ids.append(business_id)

    # Fetch uncached businesses from database
    if uncached_ids:
        print(f"→ Fetching {len(uncached_ids)} businesses from database")
        businesses = await businesses_repo.get_by_ids(uncached_ids)

        for business in businesses:
            business_map[business.id] = business

            # Cache the business
            cache_key = get_business_cache_key(f"id:{business.id}")
            set_cached(cache_key, business.model_dump(), TTL_DEFAULT)

    return [business_map.get(bid) for bid in business_ids]


def create_dataloaders() -> dict:
    """Create all DataLoaders for the GraphQL context."""
    return {
        "products_by_branch_loader": DataLoader(load_fn=load_products_for_branches),
        "branch_loader": DataLoader(load_fn=load_branches),
        "business_loader": DataLoader(load_fn=load_businesses),
    }
