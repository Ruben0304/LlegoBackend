"""GraphQL type definitions for Product entity."""
import strawberry
from datetime import datetime
from typing import Optional

from utils.s3 import generate_presigned_url
from schema.branches.types import BranchType
from schema.businesses.types import BusinessType
from models import branches_repo, businesses_repo


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
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the product image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)

    @strawberry.field(description="Branch associated with this product")
    async def branch(self) -> Optional[BranchType]:
        """Resolve the branch relationship."""
        branch_data = await branches_repo.get_by_id(self.branchId)
        if branch_data:
            return BranchType(**branch_data.model_dump())
        return None

    @strawberry.field(description="Business associated with this product (through branch)")
    async def business(self) -> Optional[BusinessType]:
        """Resolve the business relationship through branch."""
        branch_data = await branches_repo.get_by_id(self.branchId)
        if branch_data:
            business_data = await businesses_repo.get_by_id(branch_data.businessId)
            if business_data:
                return BusinessType(**business_data.model_dump())
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
    createdAt: datetime
    score: float  # Ranking score (0-1)
    distance_m: Optional[float] = None  # Distance in meters from user

    @strawberry.field(description="Presigned URL for the product image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)

    @strawberry.field(description="Distance in kilometers from user")
    def distance_km(self) -> Optional[float]:
        if self.distance_m is not None:
            return self.distance_m / 1000
        return None

    @strawberry.field(description="Branch associated with this product")
    async def branch(self) -> Optional[BranchType]:
        """Resolve the branch relationship."""
        branch_data = await branches_repo.get_by_id(self.branchId)
        if branch_data:
            return BranchType(**branch_data.model_dump())
        return None

    @strawberry.field(description="Business associated with this product (through branch)")
    async def business(self) -> Optional[BusinessType]:
        """Resolve the business relationship through branch."""
        branch_data = await branches_repo.get_by_id(self.branchId)
        if branch_data:
            business_data = await businesses_repo.get_by_id(branch_data.businessId)
            if business_data:
                return BusinessType(**business_data.model_dump())
        return None
