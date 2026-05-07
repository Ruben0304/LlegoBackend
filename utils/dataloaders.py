"""DataLoaders for efficient batch loading and avoiding N+1 queries."""

from collections import defaultdict
from typing import List, Optional

from strawberry.dataloader import DataLoader

from domain.models import Branch, Business, Product
from repositories import branches_repo, businesses_repo, product_categories_repo, products_repo
from utils.cache import (
    TTL_DEFAULT,
    get_business_cache_key,
    get_cached,
    set_cached,
)


async def load_products_for_branches(branch_ids: List[str]) -> List[List]:
    """
    Batch load products for multiple branches in a single query.
    """
    # Normalize IDs so map lookups are stable.
    branch_ids = [str(branch_id) for branch_id in branch_ids]

    # Fetch all products from database
    print(f"→ Fetching products for {len(branch_ids)} branches from database")
    all_products = await products_repo.get_by_branch_ids(branch_ids)

    # Group by branch
    products_by_branch = defaultdict(list)
    for product in all_products:
        products_by_branch[str(product.branchId)].append(product)

    return [products_by_branch.get(bid, []) for bid in branch_ids]


async def load_branches(branch_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load branches by IDs in a single query.
    """
    # Normalize IDs so map lookups are stable.
    branch_ids = [str(branch_id) for branch_id in branch_ids]

    # Fetch branches from database
    print(f"→ Fetching {len(branch_ids)} branches from database")
    branches = await branches_repo.get_by_ids(branch_ids)

    # Create map
    branch_map = {}
    for branch in branches:
        branch_map[str(branch.id)] = branch

    return [branch_map.get(bid) for bid in branch_ids]


async def load_businesses(business_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load businesses by IDs in a single query.
    Uses cache to avoid repeated queries.
    """
    # Normalize IDs so cache keys and map lookups are stable.
    business_ids = [str(business_id) for business_id in business_ids]

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
        uncached_ids = [str(business_id) for business_id in uncached_ids]
        print(f"→ Fetching {len(uncached_ids)} businesses from database")
        businesses = await businesses_repo.get_by_ids(uncached_ids)

        for business in businesses:
            business_map[str(business.id)] = business

            # Cache the business
            cache_key = get_business_cache_key(f"id:{str(business.id)}")
            set_cached(cache_key, business.model_dump(), TTL_DEFAULT)

    return [business_map.get(bid) for bid in business_ids]


async def load_product_categories(category_ids: List[str]) -> List[Optional[object]]:
    """Batch load product categories by IDs in a single query."""
    category_ids = [str(cid) for cid in category_ids]
    categories = await product_categories_repo.get_by_ids(category_ids)
    category_map = {str(c.id): c for c in categories}
    return [category_map.get(cid) for cid in category_ids]


def create_dataloaders() -> dict:
    """Create all DataLoaders for the GraphQL context."""
    return {
        "products_by_branch_loader": DataLoader(load_fn=load_products_for_branches),
        "branch_loader": DataLoader(load_fn=load_branches),
        "business_loader": DataLoader(load_fn=load_businesses),
        "category_loader": DataLoader(load_fn=load_product_categories),
    }
