"""GraphQL type definitions for Combo entity."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated, List, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import generate_presigned_url

if TYPE_CHECKING:
    from domain.models import Combo


@strawberry.type
class ComboModifierType:
    """Modificador para un producto dentro del combo."""

    name: str
    priceAdjustment: float


@strawberry.type
class ComboOptionType:
    """Producto seleccionable dentro de un slot."""

    productId: str
    isDefault: bool
    priceAdjustment: float
    availableModifiers: List[ComboModifierType]

    @strawberry.field(description="Product details")
    async def product(
        self, info: Info
    ) -> Optional[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """Resolve product details for this option."""
        from repositories import products_repo
        from schema.products.types import ProductType

        product = await products_repo.get_by_id(self.productId)
        if product:
            return ProductType(**product.model_dump(mode="json"))
        return None


@strawberry.type
class ComboSlotType:
    """Listado de productos a elegir."""

    id: str
    name: str
    description: Optional[str]
    options: List[ComboOptionType]
    minSelections: int
    maxSelections: int
    isRequired: bool
    displayOrder: int


@strawberry.enum
class DiscountType(Enum):
    """Tipo de descuento aplicable al combo."""

    NONE = "none"
    PERCENTAGE = "percentage"
    FIXED = "fixed"


@strawberry.type
class ComboType:
    """Combo personalizable de productos."""

    id: str
    branchId: str
    name: str
    description: str
    image: Optional[str]
    slots: List[ComboSlotType]
    discountType: DiscountType
    discountValue: float
    currency: str
    availability: bool
    categoryId: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Presigned URL for combo image (optional)")
    def image_url(self) -> Optional[str]:
        """Generate presigned URL for combo image."""
        if self.image:
            return generate_presigned_url(self.image)
        return None

    @strawberry.field(
        description="Representative products for frontend composition (one per slot)"
    )
    async def representative_products(
        self, info: Info
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """
        Devuelve un producto representativo por cada slot para que el frontend
        genere una imagen de composición cuando el combo no tiene foto.
        """
        from repositories import products_repo
        from schema.products.types import ProductType

        products = []
        for slot in self.slots:
            # Tomar la opción por defecto o la primera
            default_option = next(
                (opt for opt in slot.options if opt.isDefault),
                slot.options[0] if slot.options else None,
            )

            if default_option:
                product = await products_repo.get_by_id(default_option.productId)
                if product:
                    products.append(ProductType(**product.model_dump(mode="json")))

        return products

    @strawberry.field(
        description="Base price with default selections (before discount)"
    )
    async def base_price(self, info: Info) -> float:
        """Calcula el precio base sumando productos por defecto y sus ajustes."""
        from repositories import products_repo

        total = 0.0

        for slot in self.slots:
            # Tomar la opción por defecto o la primera
            default_option = next(
                (opt for opt in slot.options if opt.isDefault),
                slot.options[0] if slot.options else None,
            )

            if default_option:
                # Obtener precio del producto
                product = await products_repo.get_by_id(default_option.productId)
                if product:
                    total += product.price + default_option.priceAdjustment

        return total

    @strawberry.field(description="Final price with discount applied")
    async def final_price(self, info: Info) -> float:
        """Calcula el precio final aplicando el descuento."""
        base = await self.base_price(info)

        if self.discountType == DiscountType.PERCENTAGE:
            # Descuento en porcentaje
            return base * (1 - self.discountValue / 100)
        elif self.discountType == DiscountType.FIXED:
            # Descuento en cantidad fija
            return max(0, base - self.discountValue)
        else:
            # Sin descuento
            return base

    @strawberry.field(description="Amount saved with discount")
    async def savings(self, info: Info) -> float:
        """Calcula el ahorro total del descuento."""
        base = await self.base_price(info)
        final = await self.final_price(info)
        return max(0, base - final)

    @strawberry.field(description="Branch associated with this combo")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        """Resolve branch relationship."""
        from repositories import branches_repo
        from schema.branches.types import BranchType
        from schema.branches.utils import branch_to_dict

        branch = await branches_repo.get_by_id(self.branchId)
        if branch:
            return BranchType(**branch_to_dict(branch))
        return None


def combo_to_type(combo: "Combo") -> ComboType:
    """Convert Combo domain model to a fully typed GraphQL ComboType."""
    slots: List[ComboSlotType] = []
    for slot in combo.slots:
        options: List[ComboOptionType] = []
        for option in slot.options:
            options.append(
                ComboOptionType(
                    productId=option.productId,
                    isDefault=option.isDefault,
                    priceAdjustment=option.priceAdjustment,
                    availableModifiers=[
                        ComboModifierType(
                            name=modifier.name,
                            priceAdjustment=modifier.priceAdjustment,
                        )
                        for modifier in option.availableModifiers
                    ],
                )
            )

        slots.append(
            ComboSlotType(
                id=slot.id,
                name=slot.name,
                description=slot.description,
                options=options,
                minSelections=slot.minSelections,
                maxSelections=slot.maxSelections,
                isRequired=slot.isRequired,
                displayOrder=slot.displayOrder,
            )
        )

    try:
        discount_type = DiscountType(combo.discountType)
    except ValueError:
        discount_type = DiscountType.NONE

    return ComboType(
        id=combo.id,
        branchId=combo.branchId,
        name=combo.name,
        description=combo.description,
        image=combo.image,
        slots=slots,
        discountType=discount_type,
        discountValue=combo.discountValue,
        currency=combo.currency,
        availability=combo.availability,
        categoryId=combo.categoryId,
        createdAt=combo.createdAt,
        updatedAt=combo.updatedAt,
    )
