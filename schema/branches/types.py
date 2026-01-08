"""GraphQL type definitions for Branch entity."""
import strawberry
from typing import List, Optional, Annotated
from datetime import datetime
from enum import Enum
from strawberry.types import Info

from utils.s3 import generate_presigned_url


@strawberry.enum
class BranchTipo(Enum):
    """Tipos de establecimiento para una sucursal."""
    RESTAURANTE = "restaurante"
    DULCERIA = "dulceria"
    TIENDA = "tienda"


@strawberry.type
class CoordinatesType:
    type: str
    coordinates: List[float]


@strawberry.type
class BranchType:
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
    tipos: List[BranchTipo]
    createdAt: datetime

    @strawberry.field(description="Presigned URL for the branch avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None

    @strawberry.field(description="Presigned URL for the branch cover image")
    def cover_url(self) -> Optional[str]:
        if self.coverImage:
            return generate_presigned_url(self.coverImage)
        return None

    @strawberry.field(description="Products from this branch")
    async def products(
        self,
        info: Info,
        limit: int = 6,
        available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType
        
        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from models import products_repo
            all_products = await products_repo.get_by_branch(self.id)
        
        if available_only:
            all_products = [p for p in all_products if p.availability]
        
        return [ProductType(**p.model_dump()) for p in all_products[:limit]]


@strawberry.type
class NearbyBranchType:
    """Branch type with distance information for geospatial queries."""
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
    tipos: List[BranchTipo]
    createdAt: datetime
    distance_m: float

    @strawberry.field(description="Presigned URL for the branch avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None

    @strawberry.field(description="Presigned URL for the branch cover image")
    def cover_url(self) -> Optional[str]:
        if self.coverImage:
            return generate_presigned_url(self.coverImage)
        return None

    @strawberry.field(description="Distance in kilometers")
    def distance_km(self) -> float:
        return self.distance_m / 1000

    @strawberry.field(description="Products from this branch")
    async def products(
        self,
        info: Info,
        limit: int = 6,
        available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType
        
        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from models import products_repo
            all_products = await products_repo.get_by_branch(self.id)
        
        if available_only:
            all_products = [p for p in all_products if p.availability]
        
        return [ProductType(**p.model_dump()) for p in all_products[:limit]]


@strawberry.type
class ScoredBranchType:
    """Branch type with scoring information for ranked results."""
    id: str
    businessId: str
    name: str
    address: Optional[str]
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    avatar: Optional[str]
    coverImage: Optional[str]
    deliveryRadius: Optional[float]
    facilities: List[str]
    tipos: List[BranchTipo]
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None

    @strawberry.field(description="Presigned URL for the branch avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None

    @strawberry.field(description="Presigned URL for the branch cover image")
    def cover_url(self) -> Optional[str]:
        if self.coverImage:
            return generate_presigned_url(self.coverImage)
        return None

    @strawberry.field(description="Distance in kilometers from user")
    def distance_km(self) -> Optional[float]:
        if self.distance_m is not None:
            return self.distance_m / 1000
        return None

    @strawberry.field(description="Products from this branch")
    async def products(
        self,
        info: Info,
        limit: int = 6,
        available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType
        
        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from models import products_repo
            all_products = await products_repo.get_by_branch(self.id)
        
        if available_only:
            all_products = [p for p in all_products if p.availability]
        
        return [ProductType(**p.model_dump()) for p in all_products[:limit]]
