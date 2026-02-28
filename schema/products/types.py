"""GraphQL type definitions for Product entity."""

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import generate_presigned_url
from utils.serialization import to_strawberry_dict


@strawberry.type
class ProductType:
    id: str
    branchId: str
    name: str
    description: str
    weight: str
    price: float
    currency: str
    image: str
    availability: bool
    categoryId: Optional[str] = None
    variantListIds: list[str] = strawberry.field(default_factory=list)
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the product image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)

    @strawberry.field(description="Product category name")
    async def category_name(self, info: Info) -> Optional[str]:
        """Resolve the product category name."""
        if not self.categoryId:
            return None

        from repositories import product_categories_repo

        category_data = await product_categories_repo.get_by_id(self.categoryId)
        if category_data:
            return category_data.name
        return None

    @strawberry.field(description="Variant lists assigned to this product")
    async def variant_lists(
        self, info: Info
    ) -> list[
        Annotated["VariantListType", strawberry.lazy("schema.variant_lists.types")]
    ]:
        """Resolve the variant lists relationship."""
        if not self.variantListIds:
            return []

        from repositories import variant_lists_repo
        from schema.variant_lists.types import variant_list_to_type

        variant_lists = await variant_lists_repo.get_by_ids(self.variantListIds)
        return [variant_list_to_type(vl) for vl in variant_lists]

    @strawberry.field(description="Product category")
    async def category(
        self, info: Info
    ) -> Optional[
        Annotated[
            "ProductCategoryType", strawberry.lazy("schema.product_categories.types")
        ]
    ]:
        """Resolve the product category relationship."""
        if not self.categoryId:
            return None

        from repositories import product_categories_repo
        from schema.product_categories.types import ProductCategoryType

        category_data = await product_categories_repo.get_by_id(self.categoryId)
        if category_data:
            return ProductCategoryType(**to_strawberry_dict(category_data))
        return None

    @strawberry.field(description="Branch associated with this product")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        """Resolve the branch relationship using DataLoader."""
        from schema.branches.types import BranchTipo, BranchType, CoordinatesType

        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(str(self.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if branch_data:
            from schema.branches.utils import branch_to_dict

            return BranchType(**branch_to_dict(branch_data))
        return None

    @strawberry.field(
        description="Business associated with this product (through branch)"
    )
    async def business(
        self, info: Info
    ) -> Optional[
        Annotated["BusinessType", strawberry.lazy("schema.businesses.types")]
    ]:
        """Resolve the business relationship using DataLoaders."""
        from schema.businesses.types import BusinessType

        branch_loader = info.context.get("branch_loader")
        if branch_loader:
            branch_data = await branch_loader.load(str(self.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if not branch_data:
            return None

        business_loader = info.context.get("business_loader")
        if business_loader:
            business_data = await business_loader.load(str(branch_data.businessId))
        else:
            from repositories import businesses_repo

            business_data = await businesses_repo.get_by_id(branch_data.businessId)

        if business_data:
            return BusinessType(**to_strawberry_dict(business_data))
        return None


@strawberry.type
class ScoredProductType:
    """Product with scoring information for ranked results."""

    id: str
    branchId: str
    name: str
    description: str
    weight: str
    price: float
    currency: str
    image: str
    availability: bool
    categoryId: Optional[str] = None
    variantListIds: list[str] = strawberry.field(default_factory=list)
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None

    @strawberry.field(description="Presigned URL for the product image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)

    @strawberry.field(description="Distance in kilometers from user")
    def distance_km(self) -> Optional[float]:
        if self.distance_m is not None:
            return self.distance_m / 1000
        return None

    @strawberry.field(description="Product category name")
    async def category_name(self, info: Info) -> Optional[str]:
        """Resolve the product category name."""
        if not self.categoryId:
            return None

        from repositories import product_categories_repo

        category_data = await product_categories_repo.get_by_id(self.categoryId)
        if category_data:
            return category_data.name
        return None

    @strawberry.field(description="Variant lists assigned to this product")
    async def variant_lists(
        self, info: Info
    ) -> list[
        Annotated["VariantListType", strawberry.lazy("schema.variant_lists.types")]
    ]:
        """Resolve the variant lists relationship."""
        if not self.variantListIds:
            return []

        from repositories import variant_lists_repo
        from schema.variant_lists.types import variant_list_to_type

        variant_lists = await variant_lists_repo.get_by_ids(self.variantListIds)
        return [variant_list_to_type(vl) for vl in variant_lists]

    @strawberry.field(description="Product category")
    async def category(
        self, info: Info
    ) -> Optional[
        Annotated[
            "ProductCategoryType", strawberry.lazy("schema.product_categories.types")
        ]
    ]:
        """Resolve the product category relationship."""
        if not self.categoryId:
            return None

        from repositories import product_categories_repo
        from schema.product_categories.types import ProductCategoryType

        category_data = await product_categories_repo.get_by_id(self.categoryId)
        if category_data:
            return ProductCategoryType(**to_strawberry_dict(category_data))
        return None

    @strawberry.field(description="Branch associated with this product")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        """Resolve the branch relationship using DataLoader."""
        from schema.branches.types import BranchTipo, BranchType, CoordinatesType

        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(str(self.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if branch_data:
            from schema.branches.utils import branch_to_dict

            return BranchType(**branch_to_dict(branch_data))
        return None

    @strawberry.field(
        description="Business associated with this product (through branch)"
    )
    async def business(
        self, info: Info
    ) -> Optional[
        Annotated["BusinessType", strawberry.lazy("schema.businesses.types")]
    ]:
        """Resolve the business relationship using DataLoaders."""
        from schema.businesses.types import BusinessType

        branch_loader = info.context.get("branch_loader")
        if branch_loader:
            branch_data = await branch_loader.load(str(self.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if not branch_data:
            return None

        business_loader = info.context.get("business_loader")
        if business_loader:
            business_data = await business_loader.load(str(branch_data.businessId))
        else:
            from repositories import businesses_repo

            business_data = await businesses_repo.get_by_id(branch_data.businessId)

        if business_data:
            return BusinessType(**to_strawberry_dict(business_data))
        return None


@strawberry.type
class ProductRecommendationType:
    """Single product recommendation with reasoning."""

    product_id: str
    product_name: str
    reasoning: str

    @strawberry.field(description="Full product details")
    async def product(self, info: Info) -> Optional[ProductType]:
        """Resolve the full product details."""
        from repositories import products_repo

        product_data = await products_repo.get_by_id(self.product_id)
        if product_data:
            return ProductType(**to_strawberry_dict(product_data))
        return None


@strawberry.type
class ProductRecommendationsResponseType:
    """AI-powered complementary product recommendations."""

    recommendations: list[ProductRecommendationType]
    reasoning: str
