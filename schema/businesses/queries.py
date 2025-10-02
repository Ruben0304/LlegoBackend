"""GraphQL query resolvers for Business entity."""
import strawberry
from typing import List, Optional

from .types import BusinessType
from models import businesses_repo


@strawberry.type
class BusinessQuery:
    @strawberry.field(description="Lista de negocios")
    async def businesses(self, ownerId: Optional[str] = None) -> List[BusinessType]:
        if ownerId:
            businesses = await businesses_repo.get_by_owner(ownerId)
        else:
            businesses = await businesses_repo.get_all()
        return [BusinessType(**b.model_dump()) for b in businesses]

    @strawberry.field(description="Obtener negocio por ID")
    async def business(self, id: str) -> Optional[BusinessType]:
        business = await businesses_repo.get_by_id(id)
        return BusinessType(**business.model_dump()) if business else None

    @strawberry.field(description="Buscar negocios")
    async def search_businesses(self, query: str) -> List[BusinessType]:
        businesses = await businesses_repo.search(query)
        return [BusinessType(**b.model_dump()) for b in businesses]
