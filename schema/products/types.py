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
