"""DataLoaders for efficient batch loading and avoiding N+1 queries."""
from collections import defaultdict
from typing import List
from strawberry.dataloader import DataLoader

from models import products_repo


async def load_products_for_branches(branch_ids: List[str]) -> List[List[dict]]:
    """
    Batch load products for multiple branches in a single query.
    
    This prevents N+1 queries when fetching products for multiple branches.
    
    Args:
        branch_ids: List of branch IDs to load products for
        
    Returns:
        List of product lists, one for each branch_id in the same order
    """
    # Get all products for all branches in one query
    all_products = await products_repo.get_by_branch_ids(branch_ids)
    
    # Group products by branch_id
    products_by_branch = defaultdict(list)
    for product in all_products:
        products_by_branch[product.branchId].append(product)
    
    # Return in the same order as branch_ids
    return [products_by_branch.get(bid, []) for bid in branch_ids]


def create_dataloaders() -> dict:
    """Create all DataLoaders for the GraphQL context."""
    return {
        "products_by_branch_loader": DataLoader(load_fn=load_products_for_branches)
    }
