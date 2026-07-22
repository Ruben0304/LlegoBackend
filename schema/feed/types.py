"""GraphQL type definitions for Feed."""

from datetime import datetime
from typing import Annotated, List, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import get_public_image_variant_url, get_public_url


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
    variantListIds: List[str] = strawberry.field(default_factory=list)
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None
    updatedAt: Optional[datetime] = None

    @strawberry.field(description="Public URL for the product image")
    def image_url(self) -> str:
        return get_public_url(self.image)

    @strawberry.field(description="Public URL for the very low quality product image (200x200)")
    def image_url_muy_baja(self) -> str:
        return get_public_image_variant_url(self.image, "muy_baja")

    @strawberry.field(description="Public URL for the low quality product image (720x540)")
    def image_url_baja(self) -> str:
        return get_public_image_variant_url(self.image, "baja")

    @strawberry.field(description="Public URL for the medium quality product image (1080x1350)")
    def image_url_media(self) -> str:
        return get_public_image_variant_url(self.image, "media")

    @strawberry.field(description="Public URL for the high quality product image (1440x1800)")
    def image_url_alta(self) -> str:
        return get_public_image_variant_url(self.image, "alta")

    @strawberry.field(description="Public URL for the original product image")
    def image_url_original(self) -> str:
        return get_public_url(self.image)

    @strawberry.field(description="Product category name")
    async def category_name(self, info: Info) -> Optional[str]:
        if not self.categoryId:
            return None

        loader = info.context.get("category_loader")
        if loader:
            category_data = await loader.load(str(self.categoryId))
        else:
            from repositories import product_categories_repo
            category_data = await product_categories_repo.get_by_id(self.categoryId)

        return category_data.name if category_data else None

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


@strawberry.type
class FeedSection:
    """A section of the feed with products."""

    title: str
    section_id: str
    description: Optional[str]
    products: List[FeedProductType]
    total_count: int


@strawberry.type
class FeedCreativeType:
    """A paid, business-designed creative (Destacado / Oferta) for the feed.

    The creative is a single exported photo (the branch avatar and texts are
    baked into it by the Canva-style editor); the client just shows the image
    and opens ``ctaDeeplink`` on tap.
    """

    campaignId: str
    branchId: str
    businessId: str
    placement: str
    imageUrl: str
    ctaDeeplink: Optional[str] = None


@strawberry.type
class FeedCreativeSection:
    """A feed section made of paid creatives instead of products."""

    title: str
    section_id: str
    items: List[FeedCreativeType]


@strawberry.type
class FeedResponse:
    """Complete feed response with multiple sections."""

    sections: List[FeedSection]
    section_diagnostics: List["FeedSectionDiagnostic"]
    timestamp: datetime
    has_more: bool = False
    explorar_has_more: bool = False
    creative_sections: List[FeedCreativeSection] = strawberry.field(
        default_factory=list
    )


@strawberry.type
class FeedSectionDiagnostic:
    """Diagnostic information for each feed section request."""

    section_id: str
    title: str
    status: str
    reason: Optional[str] = None
    total_before_dedup: Optional[int] = None
    total_after_dedup: Optional[int] = None
