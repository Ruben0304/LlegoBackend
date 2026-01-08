"""GraphQL type definitions for Product entity."""
import strawberry
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from strawberry.types import Info

from utils.s3 import generate_presigned_url

if TYPE_CHECKING:
    from schema.branches.types import BranchType
    from schema.businesses.types import BusinessType


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
    async def branch(self, info: Info) -> Optional["BranchType"]:
        """Resolve the branch relationship using DataLoader."""
        from schema.branches.types import BranchType, CoordinatesType, BranchTipo
        
        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(self.branchId)
        else:
            from models import branches_repo
            branch_data = await branches_repo.get_by_id(self.branchId)
        
        if branch_data:
            return BranchType(
                **{
                    **branch_data.model_dump(),
                    'coordinates': CoordinatesType(**branch_data.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (branch_data.tipos or [])]
                }
            )
        return None

    @strawberry.field(description="Business associated with this product (through branch)")
    async def business(self, info: Info) -> Optional["BusinessType"]:
        """Resolve the business relationship using DataLoaders."""
        from schema.businesses.types import BusinessType
        
        # First get the branch
        branch_loader = info.context.get("branch_loader")
        if branch_loader:
            branch_data = await branch_loader.load(self.branchId)
        else:
            from models import branches_repo
            branch_data = await branches_repo.get_by_id(self.branchId)
        
        if not branch_data:
            return None
        
        # Then get the business
        business_loader = info.context.get("business_loader")
        if business_loader:
            business_data = await business_loader.load(branch_data.businessId)
        else:
            from models import businesses_repo
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
    async def branch(self, info: Info) -> Optional["BranchType"]:
        """Resolve the branch relationship using DataLoader."""
        from schema.branches.types import BranchType, CoordinatesType, BranchTipo
        
        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(self.branchId)
        else:
            from models import branches_repo
            branch_data = await branches_repo.get_by_id(self.branchId)
        
        if branch_data:
            return BranchType(
                **{
                    **branch_data.model_dump(),
                    'coordinates': CoordinatesType(**branch_data.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (branch_data.tipos or [])]
                }
            )
        return None

    @strawberry.field(description="Business associated with this product (through branch)")
    async def business(self, info: Info) -> Optional["BusinessType"]:
        """Resolve the business relationship using DataLoaders."""
        from schema.businesses.types import BusinessType
        
        # First get the branch
        branch_loader = info.context.get("branch_loader")
        if branch_loader:
            branch_data = await branch_loader.load(self.branchId)
        else:
            from models import branches_repo
            branch_data = await branches_repo.get_by_id(self.branchId)
        
        if not branch_data:
            return None
        
        # Then get the business
        business_loader = info.context.get("business_loader")
        if business_loader:
            business_data = await business_loader.load(branch_data.businessId)
        else:
            from models import businesses_repo
            business_data = await businesses_repo.get_by_id(branch_data.businessId)
        
        if business_data:
            return BusinessType(**business_data.model_dump())
        return None
