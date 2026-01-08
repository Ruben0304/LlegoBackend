"""DataLoaders for efficient batch loading and avoiding N+1 queries."""
from collections import defaultdict
from typing import List, Optional
from strawberry.dataloader import DataLoader

from models import products_repo, branches_repo, businesses_repo


async def load_products_for_branches(branch_ids: List[str]) -> List[List]:
    """
    Batch load products for multiple branches in a single query.
    """
    all_products = await products_repo.get_by_branch_ids(branch_ids)
    
    products_by_branch = defaultdict(list)
    for product in all_products:
        products_by_branch[product.branchId].append(product)
    
    return [products_by_branch.get(bid, []) for bid in branch_ids]


async def load_branches(branch_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load branches by IDs in a single query.
    """
    branches = await branches_repo.get_by_ids(branch_ids)
    
    branch_map = {b.id: b for b in branches}
    
    return [branch_map.get(bid) for bid in branch_ids]


async def load_businesses(business_ids: List[str]) -> List[Optional[object]]:
    """
    Batch load businesses by IDs in a single query.
    """
    businesses = await businesses_repo.get_by_ids(business_ids)
    
    business_map = {b.id: b for b in businesses}
    
    return [business_map.get(bid) for bid in business_ids]


def create_dataloaders() -> dict:
    """Create all DataLoaders for the GraphQL context."""
    return {
        "products_by_branch_loader": DataLoader(load_fn=load_products_for_branches),
        "branch_loader": DataLoader(load_fn=load_branches),
        "business_loader": DataLoader(load_fn=load_businesses),
    }
