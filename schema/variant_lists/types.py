"""GraphQL type definitions for VariantList entity."""

from datetime import datetime
from typing import Annotated, List, Optional

import strawberry
from strawberry.types import Info

from utils.serialization import to_strawberry_dict


@strawberry.type
class VariantOptionType:
    """Opción individual dentro de una lista de variantes."""

    id: str
    name: str
    priceAdjustment: float


@strawberry.type
class VariantListType:
    """Lista de variantes reutilizable por sucursal."""

    id: str
    branchId: str
    name: str
    description: Optional[str]
    options: List[VariantOptionType]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Branch associated with this variant list")
    async def branch(
        self, info: Info
    ) -> Optional[
        Annotated["BranchType", strawberry.lazy("schema.branches.types")]
    ]:
        """Resolve branch relationship."""
        from repositories import branches_repo
        from schema.branches.types import BranchType

        branch = await branches_repo.get_by_id(self.branchId)
        if branch:
            return BranchType(**to_strawberry_dict(branch))
        return None


def variant_list_to_type(variant_list) -> VariantListType:
    """Convert VariantList domain model to GraphQL type."""
    options = [
        VariantOptionType(id=opt.id, name=opt.name, priceAdjustment=opt.priceAdjustment)
        for opt in variant_list.options
    ]

    return VariantListType(
        id=str(variant_list.id),
        branchId=str(variant_list.branchId),
        name=variant_list.name,
        description=variant_list.description,
        options=options,
        createdAt=variant_list.createdAt,
        updatedAt=variant_list.updatedAt,
    )
