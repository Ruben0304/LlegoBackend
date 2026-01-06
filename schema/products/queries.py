"""GraphQL query resolvers for Product entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import ProductType, ScoredProductType
from models import products_repo
from utils.graphql_auth import apply_optional_jwt
from services.scoring_service import scoring_service


@strawberry.type
class ProductQuery:
    @strawberry.field(description="Lista de productos con scoring por cercanía")
    async def products(
        self,
        info: Info,
        ids: Optional[List[str]] = None,
        branchId: Optional[str] = None,
        categoryId: Optional[str] = None,
        availableOnly: bool = False,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None
    ) -> List[ScoredProductType]:
        """
        Get products with proximity scoring.
        
        If jwt is provided and user has location, results are scored by proximity.
        If radiusKm is provided, only products from branches within that radius are returned.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        
        # Get products based on filters
        if ids:
            products = await products_repo.get_by_ids(ids)
        elif branchId:
            products = await products_repo.get_by_branch(branchId)
        elif categoryId:
            products = await products_repo.get_by_category(categoryId)
        elif availableOnly:
            products = await products_repo.get_available()
        else:
            products = await products_repo.get_all()
        
        # If user is authenticated, apply scoring
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                scored_items = await scoring_service.score_products_by_branch(
                    products=products,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                return [
                    ScoredProductType(
                        **item.item.model_dump(),
                        score=item.score,
                        distance_m=item.distance_m
                    )
                    for item in scored_items
                ]
        
        # No user location - return without scoring (score=0, no distance)
        return [
            ScoredProductType(**p.model_dump(), score=0.0, distance_m=None)
            for p in products
        ]

    @strawberry.field(description="Obtener producto por ID")
    async def product(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[ProductType]:
        apply_optional_jwt(jwt, info)
        product = await products_repo.get_by_id(id)
        return ProductType(**product.model_dump()) if product else None

    @strawberry.field(description="Buscar productos con scoring por cercanía")
    async def search_products(
        self,
        info: Info,
        query: str,
        limit: int = 10,
        use_vector_search: bool = True,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None
    ) -> List[ScoredProductType]:
        """
        Search products with proximity scoring.
        
        If jwt is provided and user has location, results are scored by proximity.
        If radiusKm is provided, only products from branches within that radius are returned.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        
        if use_vector_search:
            from services.vector_search_service import VectorSearchService
            vector_service = VectorSearchService()
            product_ids = await vector_service.search_products(query, limit=limit)
            
            products = []
            for product_id in product_ids:
                product = await products_repo.get_by_id(product_id)
                if product:
                    products.append(product)
        else:
            products = await products_repo.search(query)
        
        # If user is authenticated, apply scoring
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                scored_items = await scoring_service.score_products_by_branch(
                    products=products,
                    user_location=user_location,
                    radius_km=radiusKm
                )
                
                return [
                    ScoredProductType(
                        **item.item.model_dump(),
                        score=item.score,
                        distance_m=item.distance_m
                    )
                    for item in scored_items
                ]
        
        # No user location - return without scoring
        return [
            ScoredProductType(**p.model_dump(), score=0.0, distance_m=None)
            for p in products
        ]
