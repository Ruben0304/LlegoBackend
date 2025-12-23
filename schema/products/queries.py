"""GraphQL query resolvers for Product entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import ProductType
from models import products_repo
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class ProductQuery:
    @strawberry.field(description="Lista de productos")
    async def products(
        self,
        info: Info,
        ids: Optional[List[str]] = None,
        branchId: Optional[str] = None,
        categoryId: Optional[str] = None,
        availableOnly: bool = False,
        jwt: Optional[str] = None
    ) -> List[ProductType]:
        apply_optional_jwt(jwt, info)
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
        return [ProductType(**p.model_dump()) for p in products]

    @strawberry.field(description="Obtener producto por ID")
    async def product(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[ProductType]:
        apply_optional_jwt(jwt, info)
        product = await products_repo.get_by_id(id)
        return ProductType(**product.model_dump()) if product else None

    @strawberry.field(description="Buscar productos")
    async def search_products(
        self,
        info: Info,
        query: str,
        limit: int = 10,
        use_vector_search: bool = True,
        jwt: Optional[str] = None
    ) -> List[ProductType]:
        apply_optional_jwt(jwt, info)
        if use_vector_search:
            # Use vector search
            from services.vector_search_service import VectorSearchService

            vector_service = VectorSearchService()
            product_ids = await vector_service.search_products(query, limit=limit)

            # Fetch products by IDs maintaining order
            products = []
            for product_id in product_ids:
                product = await products_repo.get_by_id(product_id)
                if product:
                    products.append(product)

            return [ProductType(**p.model_dump()) for p in products]
        else:
            # Use traditional text search
            products = await products_repo.search(query)
            return [ProductType(**p.model_dump()) for p in products]
