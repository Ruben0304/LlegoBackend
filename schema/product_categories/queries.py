"""GraphQL query resolvers for ProductCategory entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, product_categories_repo, products_repo
from utils.serialization import to_strawberry_dict

from .types import ProductCategoryType


@strawberry.type
class ProductCategoryQuery:
    @strawberry.field(description="Get all product categories")
    async def product_categories(
        self, info: Info, branchType: Optional[str] = None
    ) -> List[ProductCategoryType]:
        """
        Get product categories, optionally filtered by branch type.

        Args:
            branchType: Filter categories by branch type (restaurante, dulceria, tienda, perfumeria)
        """
        if branchType:
            categories = await product_categories_repo.get_by_branch_type(branchType)
        else:
            categories = await product_categories_repo.get_all()

        return [ProductCategoryType(**to_strawberry_dict(cat)) for cat in categories]

    @strawberry.field(description="Get product category by ID")
    async def product_category(
        self, info: Info, id: str
    ) -> Optional[ProductCategoryType]:
        """Get a specific product category by ID."""
        category = await product_categories_repo.get_by_id(id)
        return ProductCategoryType(**to_strawberry_dict(category)) if category else None

    @strawberry.field(description="Get product categories for a branch")
    async def branch_product_categories(
        self, info: Info, branchId: str, onlyUsed: bool = False
    ) -> List[ProductCategoryType]:
        """
        Get product categories for a branch based on its tipos.

        Args:
            branchId: Branch ID
            onlyUsed: If True, only returns categories currently used by products in the branch
        """
        branch = await branches_repo.get_by_id(branchId)
        if not branch or not branch.tipos:
            return []

        categories = await product_categories_repo.get_by_branch_types(branch.tipos)
        if not onlyUsed:
            return [ProductCategoryType(**to_strawberry_dict(cat)) for cat in categories]

        products = await products_repo.get_by_branch(branchId)
        used_category_ids = {
            str(product.categoryId) for product in products if product.categoryId
        }
        if not used_category_ids:
            return []

        filtered_categories = [cat for cat in categories if cat.id in used_category_ids]
        return [ProductCategoryType(**to_strawberry_dict(cat)) for cat in filtered_categories]
