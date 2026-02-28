"""GraphQL query resolvers for Category entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import categories_repo
from utils.graphql_auth import apply_optional_jwt

from .types import CategoryType


@strawberry.type
class CategoryQuery:
    @strawberry.field(description="Lista de categorías con subcategorías")
    async def categories(
        self, info: Info, jwt: Optional[str] = None
    ) -> List[CategoryType]:
        apply_optional_jwt(jwt, info)
        categories = await categories_repo.get_all()
        return [CategoryType(**c.model_dump(mode="json")) for c in categories]

    @strawberry.field(description="Obtener categoría por ID")
    async def category(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> Optional[CategoryType]:
        apply_optional_jwt(jwt, info)
        category = await categories_repo.get_by_id(id)
        return CategoryType(**category.model_dump(mode="json")) if category else None
