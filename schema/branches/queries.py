"""GraphQL query resolvers for Branch entity."""
import strawberry
from typing import List, Optional

from .types import BranchType, CoordinatesType
from models import branches_repo


@strawberry.type
class BranchQuery:
    @strawberry.field(description="Lista de sucursales")
    async def branches(self, businessId: Optional[str] = None) -> List[BranchType]:
        if businessId:
            branches = await branches_repo.get_by_business(businessId)
        else:
            branches = await branches_repo.get_all()
        return [BranchType(
            **{**b.model_dump(), 'coordinates': CoordinatesType(**b.coordinates.model_dump())}
        ) for b in branches]

    @strawberry.field(description="Obtener sucursal por ID")
    async def branch(self, id: str) -> Optional[BranchType]:
        branch = await branches_repo.get_by_id(id)
        if branch:
            return BranchType(
                **{**branch.model_dump(), 'coordinates': CoordinatesType(**branch.coordinates.model_dump())}
            )
        return None

    @strawberry.field(description="Buscar sucursales")
    async def search_branches(
        self,
        query: str,
        limit: int = 10,
        use_vector_search: bool = True
    ) -> List[BranchType]:
        if use_vector_search:
            # Use vector search
            from services.vector_search_service import VectorSearchService

            vector_service = VectorSearchService()
            branch_ids = await vector_service.search_branches(query, limit=limit)

            # Fetch branches by IDs maintaining order
            branches = []
            for branch_id in branch_ids:
                branch = await branches_repo.get_by_id(branch_id)
                if branch:
                    branches.append(branch)

            return [BranchType(
                **{**b.model_dump(), 'coordinates': CoordinatesType(**b.coordinates.model_dump())}
            ) for b in branches]
        else:
            # Use traditional text search
            branches = await branches_repo.search(query)
            return [BranchType(
                **{**b.model_dump(), 'coordinates': CoordinatesType(**b.coordinates.model_dump())}
            ) for b in branches]
