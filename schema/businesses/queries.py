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
        limit: int = 10,
        use_vector_search: bool = True,
        jwt: Optional[str] = None
    ) -> List[BusinessType]:
        apply_optional_jwt(jwt, info)
        if use_vector_search:
            # Use vector search
            from services.vector_search_service import VectorSearchService

            vector_service = VectorSearchService()
            business_ids = await vector_service.search_businesses(query, limit=limit)

            # Fetch businesses by IDs maintaining order
            businesses = []
            for business_id in business_ids:
                business = await businesses_repo.get_by_id(business_id)
                if business:
                    businesses.append(business)

            return [BusinessType(**b.model_dump()) for b in businesses]
        else:
            # Use traditional text search
            businesses = await businesses_repo.search(query)
            return [BusinessType(**b.model_dump()) for b in businesses]
