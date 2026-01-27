"""GraphQL query resolvers for Business entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import BusinessType, BusinessWithBranchesType
from models import businesses_repo
from repositories import searches_repo, branches_repo
from schema.branches.types import BranchType, CoordinatesType, BranchTipo
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

        # Priority-based filtering:
        # 1. If explicit ownerId provided -> use it
        # 2. If no ownerId but authenticated (user_id in context) -> filter by authenticated user
        # 3. If no ownerId and not authenticated -> return all (public query)
        if ownerId:
            # Explicit ownerId takes priority (for admin or specific queries)
            businesses = await businesses_repo.get_by_owner(ownerId)
        elif info.context.get("user_id"):
            # Authenticated user without explicit ownerId -> filter by their user_id
            user_id = info.context["user_id"]
            businesses = await businesses_repo.get_by_owner(user_id)
        else:
            # No ownerId and not authenticated -> return all (public query)
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
        user_id = info.context.get("user_id")

        # Save search to database if user is authenticated
        if user_id:
            await searches_repo.create_search(user_id, query)

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

    @strawberry.field(description="Obtener negocios con sus sucursales anidadas (optimizado)")
    async def get_businesses_with_branches(
        self,
        info: Info,
        jwt: Optional[str] = None
    ) -> List[BusinessWithBranchesType]:
        """
        Get businesses with their branches nested in a single query.
        This is optimized to reduce round-trips to the server.
        Only returns businesses owned by the authenticated user.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        
        if not user_id:
            raise Exception("Usuario no autenticado")
        
        # 1. Get businesses owned by the user
        businesses = await businesses_repo.get_by_owner(user_id)
        
        if not businesses:
            return []
        
        # 2. Get all branches for those businesses in a single query
        business_ids = [b.id for b in businesses]
        all_branches = await branches_repo.get_by_business_ids(business_ids)
        
        # 3. Group branches by businessId
        branches_by_business = {}
        for branch in all_branches:
            if branch.businessId not in branches_by_business:
                branches_by_business[branch.businessId] = []
            
            # Convert branch to BranchType
            branch_type = BranchType(
                id=branch.id,
                businessId=branch.businessId,
                name=branch.name,
                address=branch.address,
                coordinates=CoordinatesType(**branch.coordinates.model_dump()),
                phone=branch.phone,
                schedule=branch.schedule,
                managerIds=branch.managerIds,
                status=branch.status,
                avatar=branch.avatar,
                coverImage=branch.coverImage,
                deliveryRadius=branch.deliveryRadius,
                facilities=branch.facilities,
                tipos=[BranchTipo(t) for t in (branch.tipos or [])],
                paymentMethodIds=branch.paymentMethodIds or [],
                createdAt=branch.createdAt,
                wallet=branch.wallet,
                walletStatus=branch.walletStatus
            )
            branches_by_business[branch.businessId].append(branch_type)
        
        # 4. Build response with nested branches
        result = []
        for business in businesses:
            branches = branches_by_business.get(business.id, [])
            result.append(BusinessWithBranchesType(
                id=business.id,
                name=business.name,
                ownerId=business.ownerId,
                globalRating=business.globalRating,
                avatar=business.avatar,
                description=business.description,
                socialMedia=business.socialMedia,
                tags=business.tags,
                isActive=business.isActive,
                createdAt=business.createdAt,
                branches=branches
            ))
        
        return result
