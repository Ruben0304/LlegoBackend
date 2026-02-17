"""GraphQL type definitions for Branch entity."""

from datetime import datetime
from enum import Enum
from typing import Annotated, List, Optional

import strawberry
from strawberry.types import Info

from schema.wallet.types import WalletBalanceType
from utils.s3 import generate_presigned_url


@strawberry.type
class TransferAccountType:
    """A bank card account for receiving CUP transfers."""

    cardNumber: str
    cardHolderName: str
    bankName: str
    isActive: bool


@strawberry.type
class QrPaymentType:
    """A QR code value for online payments (EnZona, etc.)."""

    value: str
    isActive: bool


@strawberry.type
class TransferPhoneType:
    """A phone number for mobile transfers (Transfermóvil, etc.)."""

    phone: str
    isActive: bool


@strawberry.enum
class BranchTipo(Enum):
    """Tipos de establecimiento para una sucursal."""

    RESTAURANTE = "restaurante"
    DULCERIA = "dulceria"
    TIENDA = "tienda"


@strawberry.enum
class BranchVehicle(Enum):
    """Tipos de vehículo disponibles para delivery en una sucursal."""

    MOTO = "moto"
    BICICLETA = "bicicleta"
    CARRO = "carro"
    CAMIONETA = "camioneta"
    CAMINANDO = "caminando"


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
    isActive: bool
    status: Optional[str] = None
    avatar: Optional[str]
    coverImage: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tipos: List[BranchTipo]
    paymentMethodIds: List[str]
    useAppMessaging: bool = True
    vehicles: List[BranchVehicle] = strawberry.field(default_factory=list)
    accounts: List[TransferAccountType] = strawberry.field(default_factory=list)
    qrPayments: List[QrPaymentType] = strawberry.field(default_factory=list)
    phones: List[TransferPhoneType] = strawberry.field(default_factory=list)
    deliveryRadius: Optional[float] = None
    createdAt: datetime
    wallet: WalletBalanceType
    walletStatus: str = "active"

    @strawberry.field(
        description="Presigned URL for the branch avatar (inherits from business if not set)"
    )
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
        self, info: Info, limit: int = 6, available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType

        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from repositories import products_repo

            all_products = await products_repo.get_by_branch(self.id)

        if available_only:
            all_products = [p for p in all_products if p.availability]

        return [ProductType(**p.model_dump()) for p in all_products[:limit]]

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(
        self, info: Info
    ) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.payments.types")]]:
        """Get payment methods for this branch."""
        from repositories import payment_methods_repo
        from schema.payments.types import PaymentMethodType

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
    isActive: bool
    status: Optional[str] = None
    avatar: Optional[str]
    coverImage: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tipos: List[BranchTipo]
    paymentMethodIds: List[str]
    useAppMessaging: bool = True
    vehicles: List[BranchVehicle] = strawberry.field(default_factory=list)
    accounts: List[TransferAccountType] = strawberry.field(default_factory=list)
    qrPayments: List[QrPaymentType] = strawberry.field(default_factory=list)
    phones: List[TransferPhoneType] = strawberry.field(default_factory=list)
    deliveryRadius: Optional[float] = None
    createdAt: datetime
    distance_m: float
    wallet: WalletBalanceType
    walletStatus: str = "active"

    @strawberry.field(
        description="Presigned URL for the branch avatar (inherits from business if not set)"
    )
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
        self, info: Info, limit: int = 6, available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType

        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from repositories import products_repo

            all_products = await products_repo.get_by_branch(self.id)

        if available_only:
            all_products = [p for p in all_products if p.availability]

        return [ProductType(**p.model_dump()) for p in all_products[:limit]]

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(
        self, info: Info
    ) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.payments.types")]]:
        """Get payment methods for this branch."""
        from repositories import payment_methods_repo
        from schema.payments.types import PaymentMethodType

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
    isActive: bool
    status: Optional[str] = None
    avatar: Optional[str]
    coverImage: Optional[str]
    socialMedia: Optional[strawberry.scalars.JSON]
    tipos: List[BranchTipo]
    paymentMethodIds: List[str]
    useAppMessaging: bool = True
    vehicles: List[BranchVehicle] = strawberry.field(default_factory=list)
    accounts: List[TransferAccountType] = strawberry.field(default_factory=list)
    qrPayments: List[QrPaymentType] = strawberry.field(default_factory=list)
    phones: List[TransferPhoneType] = strawberry.field(default_factory=list)
    deliveryRadius: Optional[float] = None
    createdAt: datetime
    score: float
    distance_m: Optional[float] = None
    wallet: WalletBalanceType
    walletStatus: str = "active"

    @strawberry.field(
        description="Presigned URL for the branch avatar (inherits from business if not set)"
    )
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
        self, info: Info, limit: int = 6, available_only: bool = True
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Get products for this branch using DataLoader."""
        from schema.products.types import ProductType

        loader = info.context.get("products_by_branch_loader")
        if loader:
            all_products = await loader.load(self.id)
        else:
            from repositories import products_repo

            all_products = await products_repo.get_by_branch(self.id)

        if available_only:
            all_products = [p for p in all_products if p.availability]

        return [ProductType(**p.model_dump()) for p in all_products[:limit]]

    @strawberry.field(description="Payment methods accepted by this branch")
    async def payment_methods(
        self, info: Info
    ) -> List[Annotated["PaymentMethodType", strawberry.lazy("schema.payments.types")]]:
        """Get payment methods for this branch."""
        from repositories import payment_methods_repo
        from schema.payments.types import PaymentMethodType

        if not self.paymentMethodIds:
            return []

        payment_methods = await payment_methods_repo.get_by_ids(self.paymentMethodIds)
        return [PaymentMethodType(**pm.model_dump()) for pm in payment_methods]
