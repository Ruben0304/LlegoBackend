"""GraphQL query resolvers for Branch entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import BranchType, CoordinatesType, NearbyBranchType, ScoredBranchType, BranchTipo
from models import branches_repo
from repositories import store_locations_repo, users_repo, businesses_repo, business_access_repo
from schema.pagination import (
    BranchConnection, BranchEdge, NearbyBranchConnection, NearbyBranchEdge, PageInfo,
    encode_scored_cursor, decode_scored_cursor, encode_cursor, decode_cursor
)
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql
from services.scoring_service import scoring_service
from datetime import datetime


@strawberry.type
class BranchQuery:
    @strawberry.field(description="Lista de sucursales con scoring por cercanía (paginado)")
    async def branches(
        self,
        info: Info,
        first: Optional[int] = None,
        after: Optional[str] = None,
        businessId: Optional[str] = None,
        tipo: Optional[BranchTipo] = None,
        radiusKm: Optional[float] = None,
        productCategoryId: Optional[str] = None,
        jwt: Optional[str] = None
    ) -> BranchConnection:
        """
        Get branches with proximity scoring and cursor-based pagination.
        
        Args:
            first: Number of items to fetch. If not provided, returns all items (no pagination)
            after: Cursor to fetch items after (for pagination)
            businessId: Filter by business ID
            tipo: Filter by branch type
            radiusKm: Filter by radius in km from user location
            productCategoryId: Filter by product category ID (only branches with products in this category)
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "graphql")
        user_id = info.context.get("user_id")
        
        use_pagination = first is not None
        if use_pagination:
            first = min(first, 50)

        if tipo:
            all_branches = await branches_repo.get_by_tipo(tipo.value)
        elif businessId:
            all_branches = await branches_repo.get_by_business(businessId)
        else:
            all_branches = await branches_repo.get_all()
        
        # Filter by product category if specified
        if productCategoryId:
            from models import products_repo
            # Get products with the specified category
            products_with_category = await products_repo.get_by_category(productCategoryId)
            # Get unique branch IDs from those products
            branch_ids_with_category = set(p.branchId for p in products_with_category)
            # Filter branches to only those that have products with this category
            all_branches = [b for b in all_branches if b.id in branch_ids_with_category]
        
        # Apply scoring if user is authenticated
        scored_branches: List[ScoredBranchType] = []
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                branch_ids = [b.id for b in all_branches]
                scored_items = await scoring_service.score_branches(
                    branch_ids=branch_ids,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                branch_map = {b.id: b for b in all_branches}
                
                for item in scored_items:
                    branch = branch_map.get(item.id)
                    if branch:
                        branch_data = branch.model_dump()
                        branch_data['coordinates'] = CoordinatesType(**branch.coordinates.model_dump())
                        branch_data['tipos'] = [BranchTipo(t) for t in (branch.tipos or [])]
                        branch_data['paymentMethodIds'] = branch.paymentMethodIds or []
                        branch_data['wallet'] = branch.wallet
                        branch_data['walletStatus'] = branch.walletStatus
                        scored_branches.append(ScoredBranchType(
                            **branch_data,
                            score=item.score,
                            distance_m=item.distance_m
                        ))
        
        if not scored_branches:
            scored_branches = [
                ScoredBranchType(
                    **{
                        **b.model_dump(),
                        'coordinates': CoordinatesType(**b.coordinates.model_dump()),
                        'tipos': [BranchTipo(t) for t in (b.tipos or [])],
                        'paymentMethodIds': b.paymentMethodIds or [],
                        'wallet': b.wallet,
                        'walletStatus': b.walletStatus
                    },
                    score=0.0,
                    distance_m=None
                )
                for b in all_branches
            ]
        
        total_count = len(scored_branches)
        
        # If no pagination, return all results
        if not use_pagination:
            edges = [
                BranchEdge(
                    node=branch,
                    cursor=encode_scored_cursor(branch.score, branch.id)
                )
                for branch in scored_branches
            ]
            
            page_info = PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
                total_count=total_count
            )
            
            return BranchConnection(edges=edges, page_info=page_info)
        
        # Apply cursor-based pagination
        start_index = 0
        if after:
            cursor_score, cursor_id = decode_scored_cursor(after)
            if cursor_id:
                for i, branch in enumerate(scored_branches):
                    if branch.id == cursor_id:
                        start_index = i + 1
                        break
        
        end_index = start_index + first
        paginated_branches = scored_branches[start_index:end_index]
        
        edges = [
            BranchEdge(
                node=branch,
                cursor=encode_scored_cursor(branch.score, branch.id)
            )
            for branch in paginated_branches
        ]
        
        page_info = PageInfo(
            has_next_page=end_index < total_count,
            has_previous_page=start_index > 0,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
            total_count=total_count
        )
        
        return BranchConnection(edges=edges, page_info=page_info)

    @strawberry.field(description="Obtener sucursal por ID")
    async def branch(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[BranchType]:
        apply_optional_jwt(jwt, info)
        branch = await branches_repo.get_by_id(id)
        if branch:
            return BranchType(
                **{
                    **branch.model_dump(),
                    'coordinates': CoordinatesType(**branch.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (branch.tipos or [])],
                    'paymentMethodIds': branch.paymentMethodIds or [],
                    'wallet': branch.wallet,
                    'walletStatus': branch.walletStatus
                }
            )
        return None

    @strawberry.field(description="Buscar sucursales con scoring por cercanía (paginado)")
    async def search_branches(
        self,
        info: Info,
        query: str,
        first: Optional[int] = None,
        after: Optional[str] = None,
        use_vector_search: bool = True,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None
    ) -> BranchConnection:
        """
        Search branches with proximity scoring and cursor-based pagination.
        
        Args:
            query: Search query string
            first: Number of items to fetch. If not provided, returns all items (no pagination)
            after: Cursor to fetch items after (for pagination)
            use_vector_search: Use vector search (default: True)
            radiusKm: Filter by radius in km from user location
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "search")
        user_id = info.context.get("user_id")
        
        use_pagination = first is not None
        if use_pagination:
            first = min(first, 50)
        
        if use_vector_search:
            from services.vector_search_service import VectorSearchService
            vector_service = VectorSearchService()
            branch_ids = await vector_service.search_branches(query, limit=200)
            
            all_branches = []
            for branch_id in branch_ids:
                branch = await branches_repo.get_by_id(branch_id)
                if branch:
                    all_branches.append(branch)
        else:
            all_branches = await branches_repo.search(query)
        
        # Apply scoring if user is authenticated
        scored_branches: List[ScoredBranchType] = []
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                branch_ids = [b.id for b in all_branches]
                scored_items = await scoring_service.score_branches(
                    branch_ids=branch_ids,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                branch_map = {b.id: b for b in all_branches}
                
                for item in scored_items:
                    branch = branch_map.get(item.id)
                    if branch:
                        branch_data = branch.model_dump()
                        branch_data['coordinates'] = CoordinatesType(**branch.coordinates.model_dump())
                        branch_data['tipos'] = [BranchTipo(t) for t in (branch.tipos or [])]
                        branch_data['paymentMethodIds'] = branch.paymentMethodIds or []
                        branch_data['wallet'] = branch.wallet
                        branch_data['walletStatus'] = branch.walletStatus
                        scored_branches.append(ScoredBranchType(
                            **branch_data,
                            score=item.score,
                            distance_m=item.distance_m
                        ))
        
        if not scored_branches:
            scored_branches = [
                ScoredBranchType(
                    **{
                        **b.model_dump(),
                        'coordinates': CoordinatesType(**b.coordinates.model_dump()),
                        'tipos': [BranchTipo(t) for t in (b.tipos or [])],
                        'paymentMethodIds': b.paymentMethodIds or [],
                        'wallet': b.wallet,
                        'walletStatus': b.walletStatus
                    },
                    score=0.0,
                    distance_m=None
                )
                for b in all_branches
            ]
        
        total_count = len(scored_branches)
        
        # If no pagination, return all results
        if not use_pagination:
            edges = [
                BranchEdge(
                    node=branch,
                    cursor=encode_scored_cursor(branch.score, branch.id)
                )
                for branch in scored_branches
            ]
            
            page_info = PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
                total_count=total_count
            )
            
            return BranchConnection(edges=edges, page_info=page_info)
        
        # Apply cursor-based pagination
        start_index = 0
        if after:
            cursor_score, cursor_id = decode_scored_cursor(after)
            if cursor_id:
                for i, branch in enumerate(scored_branches):
                    if branch.id == cursor_id:
                        start_index = i + 1
                        break
        
        end_index = start_index + first
        paginated_branches = scored_branches[start_index:end_index]
        
        edges = [
            BranchEdge(
                node=branch,
                cursor=encode_scored_cursor(branch.score, branch.id)
            )
            for branch in paginated_branches
        ]
        
        page_info = PageInfo(
            has_next_page=end_index < total_count,
            has_previous_page=start_index > 0,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
            total_count=total_count
        )
        
        return BranchConnection(edges=edges, page_info=page_info)


    @strawberry.field(description="Buscar sucursales cercanas por coordenadas (paginado)")
    async def nearby_branches(
        self,
        info: Info,
        longitude: float,
        latitude: float,
        first: Optional[int] = None,
        after: Optional[str] = None,
        radius_km: float = 5.0,
        only_active: bool = True,
        tipo: Optional[BranchTipo] = None,
        jwt: Optional[str] = None
    ) -> NearbyBranchConnection:
        """
        Find branches within a radius from given coordinates with cursor-based pagination.

        Args:
            longitude: Center longitude (X coordinate)
            latitude: Center latitude (Y coordinate)
            first: Number of items to fetch. If not provided, returns all items (no pagination)
            after: Cursor to fetch items after (for pagination)
            radius_km: Search radius in kilometers (default: 5km)
            only_active: Only return active branches (default: True)
            tipo: Optional filter by branch tipo

        Returns:
            Connection with branches and pagination info, ordered by proximity
        """
        apply_optional_jwt(jwt, info)
        
        use_pagination = first is not None
        if use_pagination:
            first = min(first, 50)

        # If tipo is specified, first get the branch IDs that have that tipo
        store_ids = None
        if tipo:
            store_ids = await branches_repo.get_ids_by_tipo(tipo.value)
            if not store_ids:
                return NearbyBranchConnection(edges=[], page_info=PageInfo(
                    has_next_page=False, has_previous_page=False, total_count=0
                ))

        # Get all nearby stores from MongoDB geospatial query
        nearby_stores = await store_locations_repo.find_nearby(
            longitude=longitude,
            latitude=latitude,
            radius_km=radius_km,
            only_active=only_active,
            store_ids=store_ids
        )
        
        all_branches: List[NearbyBranchType] = []
        for store in nearby_stores:
            branch = await branches_repo.get_by_id(store["store_id"])
            if branch:
                location = store.get("location", {})
                coords = location.get("coordinates", [0.0, 0.0])

                all_branches.append(NearbyBranchType(
                    id=branch.id,
                    businessId=branch.businessId,
                    name=branch.name,
                    address=branch.address,
                    coordinates=CoordinatesType(type="Point", coordinates=coords),
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
                    distance_m=store.get("distance_m", 0.0),
                    wallet=branch.wallet,
                    walletStatus=branch.walletStatus
                ))
        
        total_count = len(all_branches)
        
        # If no pagination, return all results
        if not use_pagination:
            edges = [
                NearbyBranchEdge(
                    node=branch,
                    cursor=encode_cursor(branch.id)
                )
                for branch in all_branches
            ]
            
            page_info = PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
                total_count=total_count
            )
            
            return NearbyBranchConnection(edges=edges, page_info=page_info)
        
        # Apply cursor-based pagination
        start_index = 0
        if after:
            cursor_id = decode_cursor(after)
            if cursor_id:
                for i, branch in enumerate(all_branches):
                    if branch.id == cursor_id:
                        start_index = i + 1
                        break
        
        end_index = start_index + first
        paginated_branches = all_branches[start_index:end_index]
        
        edges = [
            NearbyBranchEdge(
                node=branch,
                cursor=encode_cursor(branch.id)
            )
            for branch in paginated_branches
        ]
        
        page_info = PageInfo(
            has_next_page=end_index < total_count,
            has_previous_page=start_index > 0,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
            total_count=total_count
        )
        
        return NearbyBranchConnection(edges=edges, page_info=page_info)

    @strawberry.field(description="Obtener ubicación de una sucursal desde MongoDB")
    async def branch_location(
        self,
        info: Info,
        branch_id: str,
        jwt: Optional[str] = None
    ) -> Optional[CoordinatesType]:
        """
        Get branch location from MongoDB stores_location collection.
        
        Args:
            branch_id: The branch ID
            
        Returns:
            Coordinates or None if not found
        """
        apply_optional_jwt(jwt, info)
        
        location_doc = await store_locations_repo.get_by_store_id(branch_id)
        if location_doc:
            location = location_doc.get("location", {})
            return CoordinatesType(
                type=location.get("type", "Point"),
                coordinates=location.get("coordinates", [0.0, 0.0])
            )
        return None

    @strawberry.field(description="Obtener todas las sucursales a las que tengo acceso (propias + compartidas)")
    async def get_my_branches(
        self,
        info: Info,
        jwt: str
    ) -> List[BranchType]:
        """
        Get all branches accessible by the authenticated user.
        Includes:
        - Branches from businesses owned by the user
        - Branches with active shared access (via invitations)

        This is the recommended query for listing branches in admin/management UI.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")

        if not user_id:
            raise Exception("Usuario no autenticado")

        # 1. Get businesses owned by the user
        owned_businesses = await businesses_repo.get_by_owner(user_id)

        # 2. Get businesses with active shared access
        accesses = await business_access_repo.get_active_by_user(user_id)

        # Filter out expired accesses (in case worker hasn't run)
        now = datetime.utcnow()
        active_accesses = [
            a for a in accesses
            if a.isActive and (a.expiresAt is None or a.expiresAt > now)
        ]

        # Get business IDs from active accesses
        shared_business_ids = [a.businessId for a in active_accesses]

        # 3. Combine all business IDs
        all_business_ids = list(set(
            [b.id for b in owned_businesses] + shared_business_ids
        ))

        # 4. Get all branches for these businesses
        all_branches = []
        if all_business_ids:
            all_branches = await branches_repo.get_by_business_ids(all_business_ids)

        # 5. Convert to BranchType
        return [
            BranchType(
                **{
                    **branch.model_dump(),
                    'coordinates': CoordinatesType(**branch.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (branch.tipos or [])],
                    'paymentMethodIds': branch.paymentMethodIds or [],
                    'wallet': branch.wallet,
                    'walletStatus': branch.walletStatus
                }
            )
            for branch in all_branches
        ]
