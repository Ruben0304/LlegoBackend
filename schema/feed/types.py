"""GraphQL type definitions for Feed."""

from datetime import datetime
from typing import Annotated, List, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import generate_presigned_url


@strawberry.type
class FeedProductType:
    """Product with scoring information for feed sections."""

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
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None

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

    @strawberry.field(description="Branch associated with this product")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        """Resolve the branch relationship using DataLoader."""
        from schema.branches.types import BranchTipo, BranchType, CoordinatesType

        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(self.branchId)
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if branch_data:
            from schema.branches.utils import branch_to_dict

            return BranchType(**branch_to_dict(branch_data))
        return None


@strawberry.type
class FeedSection:
    """A section of the feed with products."""

    title: str
    section_id: str
    description: Optional[str]
    products: List[FeedProductType]
    total_count: int


@strawberry.type
class FeedResponse:
    """Complete feed response with multiple sections."""

    sections: List[FeedSection]
    section_diagnostics: List["FeedSectionDiagnostic"]
    timestamp: datetime


@strawberry.type
class FeedSectionDiagnostic:
    """Diagnostic information for each feed section request."""

    section_id: str
    title: str
    status: str
    reason: Optional[str] = None
    total_before_dedup: Optional[int] = None
    total_after_dedup: Optional[int] = None
