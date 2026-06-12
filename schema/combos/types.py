"""GraphQL type definitions for Combo entity."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated, List, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import get_public_url
from utils.serialization import to_strawberry_dict

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
            return ProductType(**to_strawberry_dict(product))
        return None


@strawberry.type
class ComboGiftOptionType:
    """Producto elegible como regalo del combo."""

    productId: str

    @strawberry.field(description="Gift product details")
    async def product(
        self, info: Info
    ) -> Optional[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        from repositories import products_repo
        from schema.products.types import ProductType

        product = await products_repo.get_by_id(self.productId)
        if product:
            return ProductType(**to_strawberry_dict(product))
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
    isFree: bool
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
    giftOptions: List[ComboGiftOptionType]
    currency: str
    availability: bool
    categoryId: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Public URL for combo image (optional)")
    def image_url(self) -> Optional[str]:
        return get_public_url(self.image) if self.image else None

    @strawberry.field(
        description="Representative products for frontend composition (max 4 products)"
    )
    async def representative_products(
        self, info: Info
    ) -> List[Annotated["ProductType", strawberry.lazy("schema.products.types")]]:
        """
        Devuelve hasta 4 productos representativos de forma inteligente:
        - Si hay 4+ slots: 1 producto por slot (primeros 4)
        - Si hay menos de 4 slots: 1 por slot + productos adicionales de slots con múltiples opciones
        - Siempre intenta devolver 4 productos para mejor composición visual
        """
        import random
        from repositories import products_repo
        from schema.products.types import ProductType

        MAX_PRODUCTS = 4
        products = []
        used_product_ids = set()

        # Paso 1: Obtener 1 producto por slot (hasta 4 slots)
        for slot in self.slots[:MAX_PRODUCTS]:
            default_option = next(
                (opt for opt in slot.options if opt.isDefault),
                slot.options[0] if slot.options else None,
            )

            if default_option:
                product = await products_repo.get_by_id(default_option.productId)
                if product:
                    products.append(ProductType(**to_strawberry_dict(product)))
                    used_product_ids.add(str(default_option.productId))

        # Paso 2: Si tenemos menos de 4 productos, intentar agregar más
        if len(products) < MAX_PRODUCTS:
            # Buscar slots con múltiples opciones
            slots_with_multiple = [
                slot for slot in self.slots if len(slot.options) > 1
            ]
            
            # Mezclar para variedad
            random.shuffle(slots_with_multiple)
            
            for slot in slots_with_multiple:
                if len(products) >= MAX_PRODUCTS:
                    break
                
                # Buscar opciones no usadas en este slot
                unused_options = [
                    opt for opt in slot.options 
                    if str(opt.productId) not in used_product_ids
                ]
                
                for option in unused_options:
                    if len(products) >= MAX_PRODUCTS:
                        break
                    
                    product = await products_repo.get_by_id(option.productId)
                    if product:
                        products.append(ProductType(**to_strawberry_dict(product)))
                        used_product_ids.add(str(option.productId))

        return products

    @strawberry.field(description="Final price with discount applied")
    async def final_price(self, info: Info) -> float:
        """Alias del precio final mínimo válido (usar para catálogo)."""
        return await self.starting_final_price(info)

    @strawberry.field(description="Amount saved with discount")
    async def savings(self, info: Info) -> float:
        """Alias del ahorro mínimo válido (usar para catálogo)."""
        return await self.starting_savings(info)

    async def _compute_starting_base_price(self, info: Info) -> float:
        """
        Calcula el precio base mínimo válido para armar el combo.
        Respeta minSelections y maxSelections de cada slot.
        Construye la combinación válida más barata posible.
        """
        from repositories import products_repo

        total = 0.0

        for slot in self.slots:
            if getattr(slot, "isFree", False):
                continue
            # Determinar cuántos productos seleccionar (mínimo requerido)
            num_selections = slot.minSelections

            if num_selections == 0:
                # Si no es obligatorio, no incluir en el precio "desde"
                continue

            # Obtener precios de todas las opciones
            option_prices = []
            for option in slot.options:
                product = await products_repo.get_by_id(option.productId)
                if product:
                    # Precio del producto + ajuste de precio de la opción
                    option_price = product.price + option.priceAdjustment
                    option_prices.append(option_price)

            # Ordenar por precio y tomar las más baratas según minSelections
            option_prices.sort()
            slot_total = sum(option_prices[:num_selections])
            total += slot_total

        return round(total, 2)

    @strawberry.field(
        description="Minimum valid final price after discount (for catalog 'From $X' display)"
    )
    async def starting_final_price(self, info: Info) -> float:
        """
        Calcula el precio final mínimo válido después de aplicar el descuento.
        Este es el precio que debe mostrarse en catálogo como 'Desde $X'.
        """
        base = await self._compute_starting_base_price(info)
        discount_value = float(self.discountValue or 0.0)

        if self.discountType == DiscountType.PERCENTAGE:
            percentage = min(max(discount_value, 0.0), 100.0)
            return round(max(0.0, base * (1 - percentage / 100)), 2)
        elif self.discountType == DiscountType.FIXED:
            return round(max(0.0, base - max(0.0, discount_value)), 2)
        else:
            return round(base, 2)

    @strawberry.field(
        description="Minimum savings amount (minimum base total - startingFinalPrice)"
    )
    async def starting_savings(self, info: Info) -> float:
        """
        Calcula el ahorro mínimo del combo.
        Diferencia entre el precio base mínimo y el precio final mínimo.
        """
        base = await self._compute_starting_base_price(info)
        final = await self.starting_final_price(info)
        return round(max(0.0, base - final), 2)

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
                    productId=str(option.productId),
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
                isFree=bool(getattr(slot, "isFree", False)),
                displayOrder=slot.displayOrder,
            )
        )

    gift_options = [
        ComboGiftOptionType(productId=str(gift_option.productId))
        for gift_option in (combo.giftOptions or [])
    ]

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
        giftOptions=gift_options,
        currency=combo.currency,
        availability=combo.availability,
        categoryId=combo.categoryId,
        createdAt=combo.createdAt,
        updatedAt=combo.updatedAt,
    )
