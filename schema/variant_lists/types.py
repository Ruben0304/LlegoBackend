"""GraphQL type definitions for VariantList entity."""

from datetime import datetime
from typing import Annotated, List, Optional

import strawberry
from strawberry.types import Info


@strawberry.type
class VariantOptionType:
    """Opción individual dentro de una lista de variantes."""

    id: str
    name: str
    priceAdjustment: float


@strawberry.type
class VariantListType:
    """Lista global de variantes reutilizable por negocio."""

    id: str
    businessId: str
    name: str
    description: Optional[str]
    options: List[VariantOptionType]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Business associated with this variant list")
    async def business(
        self, info: Info
    ) -> Optional[
        Annotated["BusinessType", strawberry.lazy("schema.businesses.types")]
    ]:
        """Resolve business relationship."""
        from repositories import businesses_repo
        from schema.businesses.types import BusinessType

        business = await businesses_repo.get_by_id(self.businessId)
        if business:
            return BusinessType(**business.model_dump(mode="json"))
        return None


def variant_list_to_type(variant_list) -> VariantListType:
    """Convert VariantList domain model to GraphQL type."""
    options = [
        VariantOptionType(id=opt.id, name=opt.name, priceAdjustment=opt.priceAdjustment)
        for opt in variant_list.options
    ]

    return VariantListType(
        id=str(variant_list.id),
        businessId=str(variant_list.businessId),
        name=variant_list.name,
        description=variant_list.description,
        options=options,
        createdAt=variant_list.createdAt,
        updatedAt=variant_list.updatedAt,
    )
