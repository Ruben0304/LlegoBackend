"""GraphQL query resolvers for Business entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import BusinessType
from models import businesses_repo
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class BusinessQuery:
    @strawberry.field(description="Lista de negocios")
    async def businesses(
        self,
        info: Info,
        ownerId: Optional[str] = None,
        jwt: Optional[str] = None
    ) -> List[BusinessType]:
        apply_optional_jwt(jwt, info)
        if ownerId:
            businesses = await businesses_repo.get_by_owner(ownerId)
        else:
            businesses = await businesses_repo.get_all()
        return [BusinessType(**b.model_dump()) for b in businesses]

    @strawberry.field(description="Obtener negocio por ID")
    async def business(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[BusinessType]:
        apply_optional_jwt(jwt, info)
        business = await businesses_repo.get_by_id(id)
        return BusinessType(**business.model_dump()) if business else None

    @strawberry.field(description="Buscar negocios")
    async def search_businesses(
        self,
        info: Info,
        query: str,
        jwt: Optional[str] = None
    ) -> List[BusinessType]:
        apply_optional_jwt(jwt, info)
        businesses = await businesses_repo.search(query)
        return [BusinessType(**b.model_dump()) for b in businesses]
