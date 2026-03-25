"""GraphQL input definitions for Combo mutations."""

from typing import List, Optional

import strawberry

from schema.combos.types import DiscountType


@strawberry.input
class ComboModifierInput:
    """Input para crear modificador de producto."""

    name: str
    priceAdjustment: float = 0.0


@strawberry.input
class ComboOptionInput:
    """Input para crear opción de producto en un slot."""

    productId: str
    isDefault: bool = False
    priceAdjustment: float = 0.0
    availableModifiers: List[ComboModifierInput] = strawberry.field(default_factory=list)


@strawberry.input
class ComboGiftOptionInput:
    """Input para configurar productos posibles de regalo."""

    productId: str


@strawberry.input
class ComboSlotInput:
    """Input para crear un slot (listado de productos)."""

    name: str
    description: Optional[str] = None
    options: List[ComboOptionInput]
    minSelections: int = 1
    maxSelections: int = 1
    isFree: bool = False
    displayOrder: int = 0


@strawberry.input
class CreateComboInput:
    """Input para crear un nuevo combo."""

    branchId: str
    name: str
    description: str
    image: Optional[str] = None
    slots: List[ComboSlotInput]
    discountType: DiscountType = DiscountType.NONE
    discountValue: float = 0.0
    giftOptions: List[ComboGiftOptionInput] = strawberry.field(default_factory=list)
    categoryId: Optional[str] = None


@strawberry.input
class UpdateComboInput:
    """Input para actualizar un combo existente."""

    comboId: str
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    slots: Optional[List[ComboSlotInput]] = None
    discountType: Optional[DiscountType] = None
    discountValue: Optional[float] = None
    giftOptions: Optional[List[ComboGiftOptionInput]] = None
    availability: Optional[bool] = None
    categoryId: Optional[str] = None
