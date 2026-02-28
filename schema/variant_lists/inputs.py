"""GraphQL input definitions for VariantList mutations."""

from typing import List, Optional

import strawberry


@strawberry.input
class VariantOptionInput:
    """Input para crear/actualizar una opción de variante."""

    id: Optional[str] = None  # Si no se proporciona, se genera automáticamente
    name: str
    priceAdjustment: float = 0.0


@strawberry.input
class CreateVariantListInput:
    """Input para crear una nueva lista de variantes."""

    businessId: str
    name: str
    description: Optional[str] = None
    options: List[VariantOptionInput]


@strawberry.input
class UpdateVariantListInput:
    """Input para actualizar una lista de variantes existente."""

    variantListId: str
    name: Optional[str] = None
    description: Optional[str] = None
    options: Optional[List[VariantOptionInput]] = None
