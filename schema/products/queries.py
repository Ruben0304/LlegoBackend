"""GraphQL query resolvers for Product entity."""
import strawberry
from typing import List, Optional

from .types import ProductType
from models import products_repo


@strawberry.type
class ProductQuery:
    @strawberry.field(description="Lista de productos")
    async def products(
        self,
        ids: Optional[List[str]] = None,
        branchId: Optional[str] = None,
        categoryId: Optional[str] = None,
        availableOnly: bool = False
    ) -> List[ProductType]:
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
    async def product(self, id: str) -> Optional[ProductType]:
        product = await products_repo.get_by_id(id)
        return ProductType(**product.model_dump()) if product else None

    @strawberry.field(description="Buscar productos")
    async def search_products(
        self,
        query: str,
        limit: int = 10,
        use_vector_search: bool = True
    ) -> List[ProductType]:
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
