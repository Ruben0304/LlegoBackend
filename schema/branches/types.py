"""GraphQL type definitions for Branch entity."""
import strawberry
from typing import List, Optional, Annotated, Dict
from datetime import datetime
from enum import Enum
from strawberry.types import Info
from strawberry import Private

from utils.s3 import generate_presigned_url
from schema.wallet.types import WalletBalanceType


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
    paymentMethodIds: List[str]
    createdAt: datetime

    # Private fields to store wallet data
    _wallet: Private[Optional[Dict[str, float]]] = None
    _wallet_status: Private[Optional[str]] = None

    @strawberry.field(description="Wallet balance de la sucursal")
    def wallet(self) -> WalletBalanceType:
        """Get wallet with default values if not exists."""
        if self._wallet:
            return WalletBalanceType(
                local=self._wallet.get('local', 0.0),
                usd=self._wallet.get('usd', 0.0)
            )
        return WalletBalanceType(local=0.0, usd=0.0)

    @strawberry.field(description="Estado de la wallet")
    def wallet_status(self) -> str:
        """Get wallet status with default value if not exists."""
        return self._wallet_status if self._wallet_status else "active"

    @strawberry.field(description="Presigned URL for the branch avatar (inherits from business if not set)")
    async def avatar_url(self, info: Info) -> Optional[str]:
        # Si la sucursal tiene avatar propio, usarlo
        if self.avatar:
            return generate_presigned_url(self.avatar)
        
        # Si no, intentar heredar del negocio padre
        from repositories import businesses_repo
        business = await businesses_repo.get_by_id(self.businessId)
        if business and business.avatar:
            return generate_presigned_url(business.avatar)
        
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

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(self, info: Info) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.ai_assistant.types")]]:
        """Get payment methods for this branch."""
        from schema.ai_assistant.types import PaymentMethodType
        from models import payment_methods_repo
        
        if not self.paymentMethodIds:
            return []
        
        payment_methods = await payment_methods_repo.get_by_ids(self.paymentMethodIds)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]


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
    paymentMethodIds: List[str]
    createdAt: datetime
    distance_m: float

    # Private fields to store wallet data
    _wallet: Private[Optional[Dict[str, float]]] = None
    _wallet_status: Private[Optional[str]] = None

    @strawberry.field(description="Wallet balance de la sucursal")
    def wallet(self) -> WalletBalanceType:
        """Get wallet with default values if not exists."""
        if self._wallet:
            return WalletBalanceType(
                local=self._wallet.get('local', 0.0),
                usd=self._wallet.get('usd', 0.0)
            )
        return WalletBalanceType(local=0.0, usd=0.0)

    @strawberry.field(description="Estado de la wallet")
    def wallet_status(self) -> str:
        """Get wallet status with default value if not exists."""
        return self._wallet_status if self._wallet_status else "active"

    @strawberry.field(description="Presigned URL for the branch avatar (inherits from business if not set)")
    async def avatar_url(self, info: Info) -> Optional[str]:
        # Si la sucursal tiene avatar propio, usarlo
        if self.avatar:
            return generate_presigned_url(self.avatar)
        
        # Si no, intentar heredar del negocio padre
        from repositories import businesses_repo
        business = await businesses_repo.get_by_id(self.businessId)
        if business and business.avatar:
            return generate_presigned_url(business.avatar)
        
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

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(self, info: Info) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.ai_assistant.types")]]:
        """Get payment methods for this branch."""
        from schema.ai_assistant.types import PaymentMethodType
        from models import payment_methods_repo
        
        if not self.paymentMethodIds:
            return []
        
        payment_methods = await payment_methods_repo.get_by_ids(self.paymentMethodIds)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]


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
    paymentMethodIds: List[str]
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None

    # Private fields to store wallet data
    _wallet: Private[Optional[Dict[str, float]]] = None
    _wallet_status: Private[Optional[str]] = None

    @strawberry.field(description="Wallet balance de la sucursal")
    def wallet(self) -> WalletBalanceType:
        """Get wallet with default values if not exists."""
        if self._wallet:
            return WalletBalanceType(
                local=self._wallet.get('local', 0.0),
                usd=self._wallet.get('usd', 0.0)
            )
        return WalletBalanceType(local=0.0, usd=0.0)

    @strawberry.field(description="Estado de la wallet")
    def wallet_status(self) -> str:
        """Get wallet status with default value if not exists."""
        return self._wallet_status if self._wallet_status else "active"

    @strawberry.field(description="Presigned URL for the branch avatar (inherits from business if not set)")
    async def avatar_url(self, info: Info) -> Optional[str]:
        # Si la sucursal tiene avatar propio, usarlo
        if self.avatar:
            return generate_presigned_url(self.avatar)
        
        # Si no, intentar heredar del negocio padre
        from repositories import businesses_repo
        business = await businesses_repo.get_by_id(self.businessId)
        if business and business.avatar:
            return generate_presigned_url(business.avatar)
        
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

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(self, info: Info) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.ai_assistant.types")]]:
        """Get payment methods for this branch."""
        from schema.ai_assistant.types import PaymentMethodType
        from models import payment_methods_repo
        
        if not self.paymentMethodIds:
            return []
        
        payment_methods = await payment_methods_repo.get_by_ids(self.paymentMethodIds)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]
