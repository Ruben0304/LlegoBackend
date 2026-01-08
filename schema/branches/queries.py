"""GraphQL query resolvers for Branch entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import BranchType, CoordinatesType, NearbyBranchType, ScoredBranchType, BranchTipo
from models import branches_repo
from repositories import store_locations_repo
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql
from services.scoring_service import scoring_service


@strawberry.type
class BranchQuery:
    @strawberry.field(description="Lista de sucursales con scoring por cercanía")
    async def branches(
        self,
        info: Info,
        businessId: Optional[str] = None,
        tipo: Optional[BranchTipo] = None,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None
    ) -> List[ScoredBranchType]:
        """Get branches with proximity scoring."""
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "graphql")
        user_id = info.context.get("user_id")

        if tipo:
            branches = await branches_repo.get_by_tipo(tipo.value)
        elif businessId:
            branches = await branches_repo.get_by_business(businessId)
        else:
            branches = await branches_repo.get_all()
        
        # If user is authenticated, apply scoring
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                branch_ids = [b.id for b in branches]
                scored_items = await scoring_service.score_branches(
                    branch_ids=branch_ids,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                # Create a map of branch data
                branch_map = {b.id: b for b in branches}
                
                results = []
                for item in scored_items:
                    branch = branch_map.get(item.id)
                    if branch:
                        branch_data = branch.model_dump()
                        branch_data['coordinates'] = CoordinatesType(**branch.coordinates.model_dump())
                        branch_data['tipos'] = [BranchTipo(t) for t in (branch.tipos or [])]
                        results.append(ScoredBranchType(
                            **branch_data,
                            score=item.score,
                            distance_m=item.distance_m
                        ))
                return results
        
        # No user location - return without scoring
        return [
            ScoredBranchType(
                **{
                    **b.model_dump(),
                    'coordinates': CoordinatesType(**b.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (b.tipos or [])]
                },
                score=0.0,
                distance_m=None
            )
            for b in branches
        ]

    @strawberry.field(description="Obtener sucursal por ID")
    async def branch(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[BranchType]:
        apply_optional_jwt(jwt, info)
        branch = await branches_repo.get_by_id(id)
        if branch:
            return BranchType(
                **{
                    **branch.model_dump(),
                    'coordinates': CoordinatesType(**branch.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (branch.tipos or [])]
                }
            )
        return None

    @strawberry.field(description="Buscar sucursales con scoring por cercanía")
    async def search_branches(
        self,
        info: Info,
        query: str,
        limit: int = 10,
        use_vector_search: bool = True,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None
    ) -> List[ScoredBranchType]:
        """Search branches with proximity scoring."""
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "search")  # 10/min - vector search is expensive
        user_id = info.context.get("user_id")
        
        if use_vector_search:
            from services.vector_search_service import VectorSearchService
            vector_service = VectorSearchService()
            branch_ids = await vector_service.search_branches(query, limit=limit)
            
            branches = []
            for branch_id in branch_ids:
                branch = await branches_repo.get_by_id(branch_id)
                if branch:
                    branches.append(branch)
        else:
            branches = await branches_repo.search(query)
        
        # If user is authenticated, apply scoring
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                branch_ids = [b.id for b in branches]
                scored_items = await scoring_service.score_branches(
                    branch_ids=branch_ids,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                results = []
                for item in scored_items:
                    branch = branch_map.get(item.id)
                    if branch:
                        branch_data = branch.model_dump()
                        branch_data['coordinates'] = CoordinatesType(**branch.coordinates.model_dump())
                        branch_data['tipos'] = [BranchTipo(t) for t in (branch.tipos or [])]
                        results.append(ScoredBranchType(
                            **branch_data,
                            score=item.score,
                            distance_m=item.distance_m
                        ))
                return results
        
        # No user location - return without scoring
        return [
            ScoredBranchType(
                **{
                    **b.model_dump(),
                    'coordinates': CoordinatesType(**b.coordinates.model_dump()),
                    'tipos': [BranchTipo(t) for t in (b.tipos or [])]
                },
                score=0.0,
                distance_m=None
            )
            for b in branches
        ]


    @strawberry.field(description="Buscar sucursales cercanas por coordenadas")
    async def nearby_branches(
        self,
        info: Info,
        longitude: float,
        latitude: float,
        radius_km: float = 5.0,
        only_active: bool = True,
        tipo: Optional[BranchTipo] = None,
        jwt: Optional[str] = None
    ) -> List[NearbyBranchType]:
        """
        Find branches within a radius from given coordinates.

        Args:
            longitude: Center longitude (X coordinate)
            latitude: Center latitude (Y coordinate)
            radius_km: Search radius in kilometers (default: 5km)
            only_active: Only return active branches (default: True)
            tipo: Optional filter by branch tipo

        Returns:
            List of branches with distance, ordered by proximity
        """
        apply_optional_jwt(jwt, info)

        # If tipo is specified, first get the branch IDs that have that tipo
        store_ids = None
        if tipo:
            store_ids = await branches_repo.get_ids_by_tipo(tipo.value)
            if not store_ids:
                return []  # No branches with this tipo

        # Get nearby stores from MongoDB geospatial query
        nearby_stores = await store_locations_repo.find_nearby(
            longitude=longitude,
            latitude=latitude,
            radius_km=radius_km,
            only_active=only_active,
            store_ids=store_ids
        )
        
        results = []
        for store in nearby_stores:
            # Get full branch data from Qdrant
            branch = await branches_repo.get_by_id(store["store_id"])
            if branch:
                # Get coordinates from MongoDB (source of truth)
                location = store.get("location", {})
                coords = location.get("coordinates", [0.0, 0.0])
                
                results.append(NearbyBranchType(
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
                    createdAt=branch.createdAt,
                    distance_m=store.get("distance_m", 0.0)
                ))
        
        return results

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
