"""GraphQL query resolvers for ProductCategory entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import product_categories_repo
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
