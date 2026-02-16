"""GraphQL query resolvers for Product entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, products_repo, searches_repo
from schema.branches.types import BranchTipo
from schema.pagination import (
    PageInfo,
    ProductConnection,
    ProductEdge,
    decode_scored_cursor,
    encode_scored_cursor,
)
from services.scoring_service import scoring_service
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql

from .types import ProductType, ScoredProductType


@strawberry.type
class ProductQuery:
    @strawberry.field(
        description="Lista de productos con scoring por cercanía (paginado)"
    )
    async def products(
        self,
        info: Info,
        first: Optional[int] = None,
        after: Optional[str] = None,
        ids: Optional[List[str]] = None,
        branchId: Optional[str] = None,
        categoryId: Optional[str] = None,
        availableOnly: bool = False,
        branchTipo: Optional[BranchTipo] = None,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None,
    ) -> ProductConnection:
        """
        Get products with proximity scoring and cursor-based pagination.

        Args:
            first: Number of items to fetch. If not provided, returns all items (no pagination)
            after: Cursor to fetch items after (for pagination)
            ids: Filter by specific product IDs
            branchId: Filter by branch ID (takes priority over branchTipo)
            categoryId: Filter by category ID
            availableOnly: Only return available products
            branchTipo: Filter by branch type (ignored if branchId is provided)
            radiusKm: Filter by radius in km from user location
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "graphql")
        user_id = info.context.get("user_id")

        # Always enforce a limit — default to 100 if not specified
        DEFAULT_PRODUCT_LIMIT = 100
        if first is None:
            first = DEFAULT_PRODUCT_LIMIT
        first = min(first, DEFAULT_PRODUCT_LIMIT)

        # Get products based on filters
        # branchId takes priority over branchTipo
        if ids:
            all_products = await products_repo.get_by_ids(ids)
        elif branchId:
            # Filter by specific branch - show ALL products (no category filter)
            all_products = await products_repo.get_feed_products(
                branch_ids=[branchId], apply_category_filter=False
            )
        elif branchTipo:
            # Filter by branch type - apply category filtering
            branch_ids = await branches_repo.get_ids_by_tipo(branchTipo.value)
            if not branch_ids:
                return ProductConnection(
                    edges=[],
                    page_info=PageInfo(
                        has_next_page=False, has_previous_page=False, total_count=0
                    ),
                )
            all_products = await products_repo.get_feed_products(
                branch_ids=branch_ids,
                apply_category_filter=True,
                requested_branch_tipo=branchTipo.value,
            )
        elif categoryId:
            all_products = await products_repo.get_by_category(categoryId)
        elif availableOnly:
            all_products = await products_repo.get_available()
        else:
            # Feed general - no category filtering (show all)
            all_products = await products_repo.get_feed_products(
                branch_ids=None, apply_category_filter=False
            )

        # Apply scoring if user is authenticated
        scored_products: List[ScoredProductType] = []
        if user_id:
            user_location = await scoring_service.get_user_location(user_id)
            if user_location:
                scored_items = await scoring_service.score_products_by_branch(
                    products=all_products,
                    user_location=user_location,
                    radius_km=radiusKm,
                )
                scored_products = [
                    ScoredProductType(
                        **item.item.model_dump(),
                        score=item.score,
                        distance_m=item.distance_m,
                    )
                    for item in scored_items
                ]

        if not scored_products:
            scored_products = [
                ScoredProductType(**p.model_dump(), score=0.0, distance_m=None)
                for p in all_products
            ]

        total_count = len(scored_products)

        # Apply cursor-based pagination
        start_index = 0
        if after:
            cursor_score, cursor_id = decode_scored_cursor(after)
            if cursor_id:
                for i, product in enumerate(scored_products):
                    if product.id == cursor_id:
                        start_index = i + 1
                        break

        # Slice the results
        end_index = start_index + first
        paginated_products = scored_products[start_index:end_index]

        # Build edges with cursors
        edges = [
            ProductEdge(
                node=product, cursor=encode_scored_cursor(product.score, product.id)
            )
            for product in paginated_products
        ]

        # Build page info
        page_info = PageInfo(
            has_next_page=end_index < total_count,
            has_previous_page=start_index > 0,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
            total_count=total_count,
        )

        return ProductConnection(edges=edges, page_info=page_info)

    @strawberry.field(description="Obtener producto por ID")
    async def product(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> Optional[ProductType]:
        apply_optional_jwt(jwt, info)

        product = await products_repo.get_by_id(id)
        return ProductType(**product.model_dump()) if product else None

    @strawberry.field(
        description="Buscar productos con scoring por cercanía (paginado)"
    )
    async def search_products(
        self,
        info: Info,
        query: str,
        first: Optional[int] = None,
        after: Optional[str] = None,
        use_vector_search: bool = True,
        branchTipo: Optional[BranchTipo] = None,
        categoryId: Optional[str] = None,
        radiusKm: Optional[float] = None,
        jwt: Optional[str] = None,
    ) -> ProductConnection:
        """
        Search products with proximity scoring and cursor-based pagination.

        Args:
            query: Search query string
            first: Number of items to fetch. If not provided, returns all items (no pagination)
            after: Cursor to fetch items after (for pagination)
            use_vector_search: Use vector search (default: True)
            branchTipo: Filter by branch type
            radiusKm: Filter by radius in km from user location
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "search")
        user_id = info.context.get("user_id")

        # Save search to database if user is authenticated
        if user_id:
            await searches_repo.create_search(user_id, query)

        DEFAULT_SEARCH_LIMIT = 50
        if first is None:
            first = DEFAULT_SEARCH_LIMIT
        first = min(first, DEFAULT_SEARCH_LIMIT)

        # Get branch IDs with the specified tipo for filtering
        allowed_branch_ids = None
        if branchTipo:
            allowed_branch_ids = set(
                await branches_repo.get_ids_by_tipo(branchTipo.value)
            )
            if not allowed_branch_ids:
                return ProductConnection(
                    edges=[],
                    page_info=PageInfo(
                        has_next_page=False, has_previous_page=False, total_count=0
                    ),
                )

        # Build allowed product IDs set from category filter
        allowed_category_ids = None
        if categoryId:
            category_products = await products_repo.get_by_category(categoryId)
            allowed_category_ids = set(p.id for p in category_products)
            if not allowed_category_ids:
                return ProductConnection(
                    edges=[],
                    page_info=PageInfo(
                        has_next_page=False, has_previous_page=False, total_count=0
                    ),
                )

        if use_vector_search:
            from services.reranking_service import reranking_service
            from services.vector_search_service import VectorSearchService

            vector_service = VectorSearchService()
            # Request more results for filtering and pagination
            search_limit = 200
            product_results = await vector_service.search_products(
                query, limit=search_limit
            )

            # Build vector scores map and product list
            vector_scores = {r.mongo_id: r.score for r in product_results}
            all_products = []

            for result in product_results:
                product = await products_repo.get_by_id(result.mongo_id)
                if product:
                    if (
                        allowed_branch_ids is not None
                        and product.branchId not in allowed_branch_ids
                    ):
                        continue
                    if (
                        allowed_category_ids is not None
                        and product.id not in allowed_category_ids
                    ):
                        continue
                    all_products.append(product)

            # RE-RANK: Combine vector search with popularity, proximity, and personalization
            user_location = None
            if user_id:
                user_location = await scoring_service.get_user_location(user_id)

            ranked_products = await reranking_service.rerank_products(
                products=all_products,
                query=query,
                user_id=user_id,
                user_location=user_location,
                vector_scores=vector_scores,
            )

            # Convert to ScoredProductType
            scored_products = [
                ScoredProductType(
                    **rp.product.model_dump(),
                    score=rp.final_score,
                    distance_m=None,  # Could extract from proximity_score if needed
                )
                for rp in ranked_products
            ]
        else:
            all_products = await products_repo.search(query)
            if allowed_branch_ids is not None:
                all_products = [
                    p for p in all_products if p.branchId in allowed_branch_ids
                ]
            if allowed_category_ids is not None:
                all_products = [p for p in all_products if p.id in allowed_category_ids]

            # Fallback: simple scoring without re-ranking
            scored_products = [
                ScoredProductType(**p.model_dump(), score=0.0, distance_m=None)
                for p in all_products
            ]

        total_count = len(scored_products)

        # Apply cursor-based pagination
        start_index = 0
        if after:
            cursor_score, cursor_id = decode_scored_cursor(after)
            if cursor_id:
                for i, product in enumerate(scored_products):
                    if product.id == cursor_id:
                        start_index = i + 1
                        break

        end_index = start_index + first
        paginated_products = scored_products[start_index:end_index]

        edges = [
            ProductEdge(
                node=product, cursor=encode_scored_cursor(product.score, product.id)
            )
            for product in paginated_products
        ]

        page_info = PageInfo(
            has_next_page=end_index < total_count,
            has_previous_page=start_index > 0,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
            total_count=total_count,
        )

        return ProductConnection(edges=edges, page_info=page_info)
