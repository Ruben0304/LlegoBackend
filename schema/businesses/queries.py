"""GraphQL query resolvers for Business entity."""

from datetime import datetime
from typing import List, Optional

import strawberry
from strawberry.types import Info

from domain.models import businesses_repo
from repositories import branches_repo, searches_repo
from schema.branches.types import BranchTipo, BranchType, CoordinatesType
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import generate_presigned_url

from .types import BusinessType


@strawberry.type
class BusinessWithBranchesType:
    """Business type with nested branches and access metadata."""

    id: str
    name: str
    ownerId: str
    globalRating: float
    avatar: Optional[str]
    description: Optional[str]
    tags: Optional[List[str]]
    isActive: bool
    createdAt: datetime
    branches: List[BranchType]
    isOwner: bool  # True if user is the owner, False if invited
    role: str  # "owner", "manager", or "employee"

    @strawberry.field(description="Presigned URL for the business avatar")
    def avatar_url(self) -> Optional[str]:
        if self.avatar:
            return generate_presigned_url(self.avatar)
        return None


@strawberry.type
class BusinessQuery:
    @strawberry.field(description="Lista de negocios (query pública/admin)")
    async def businesses(
        self, info: Info, ownerId: Optional[str] = None, jwt: Optional[str] = None
    ) -> List[BusinessType]:
        """
        Public/admin query for businesses.
        For user-specific queries, use getMyBusinessesWithBranches instead.
        """
        apply_optional_jwt(jwt, info)

        if ownerId:
            businesses = await businesses_repo.get_by_owner(ownerId)
        else:
            businesses = await businesses_repo.get_all()

        return [BusinessType(**b.model_dump()) for b in businesses]

    @strawberry.field(description="Obtener negocio por ID")
    async def business(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> Optional[BusinessType]:
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
        jwt: Optional[str] = None,
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

    @strawberry.field(
        description="Obtener todos mis negocios con sucursales (propios + compartidos)"
    )
    async def get_my_businesses_with_branches(
        self, info: Info, jwt: str
    ) -> List[BusinessWithBranchesType]:
        """
        Get all businesses accessible by the authenticated user with their branches.

        Includes:
        - Businesses owned by the user (ownerId = user_id)
        - Businesses with active shared access (via invitations)

        Returns branches filtered by access level:
        - Owners: All branches
        - Business access: All branches
        - Branch managers: Only their assigned branches

        This is the main query for the frontend to display businesses and branches.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")

        if not user_id:
            raise Exception("Usuario no autenticado")

        from datetime import datetime

        from repositories import business_access_repo

        # 1. Get businesses owned by the user
        owned_businesses = await businesses_repo.get_by_owner(user_id)
        owned_business_ids = {b.id for b in owned_businesses}

        # 2. Get businesses with active shared access
        accesses = await business_access_repo.get_active_by_user(user_id)

        # Filter out expired accesses
        now = datetime.utcnow()
        active_accesses = [
            a
            for a in accesses
            if a.isActive and (a.expiresAt is None or a.expiresAt > now)
        ]

        # Get business IDs from active accesses
        shared_business_ids = [a.businessId for a in active_accesses]

        # Fetch shared businesses
        shared_businesses = []
        if shared_business_ids:
            shared_businesses = await businesses_repo.get_by_ids(shared_business_ids)

        # 3. Combine all businesses
        all_businesses = list(owned_businesses)
        for b in shared_businesses:
            if b.id not in owned_business_ids:
                all_businesses.append(b)

        if not all_businesses:
            return []

        # 4. Get all branches for these businesses
        business_ids = [b.id for b in all_businesses]
        all_branches = await branches_repo.get_by_business_ids(business_ids)

        # 5. Filter branches by access level and group by businessId
        branches_by_business = {}
        for branch in all_branches:
            business_id = branch.businessId

            # Determine if user has access to this branch
            has_access = False

            # Owner has access to all branches
            if business_id in owned_business_ids:
                has_access = True
            # Business access grants access to all branches
            elif business_id in shared_business_ids:
                has_access = True
            # Branch manager has access only to their branches
            elif user_id in branch.managerIds:
                has_access = True

            if has_access:
                if business_id not in branches_by_business:
                    branches_by_business[business_id] = []

                # Convert branch to BranchType
                from schema.branches.utils import branch_to_dict

                branch_type = BranchType(**branch_to_dict(branch))
                branches_by_business[business_id].append(branch_type)

        # 6. Build response with metadata
        result = []
        for business in all_businesses:
            is_owner = business.id in owned_business_ids

            # Determine role
            if is_owner:
                role = "owner"
            elif business.id in shared_business_ids:
                role = "manager"  # Business-level access
            else:
                role = "employee"  # Branch-level access only

            branches = branches_by_business.get(business.id, [])

            result.append(
                BusinessWithBranchesType(
                    id=business.id,
                    name=business.name,
                    ownerId=business.ownerId,
                    globalRating=business.globalRating,
                    avatar=business.avatar,
                    description=business.description,
                    tags=business.tags,
                    isActive=business.isActive,
                    createdAt=business.createdAt,
                    branches=branches,
                    isOwner=is_owner,
                    role=role,
                )
            )

        return result
