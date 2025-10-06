"""GraphQL query resolvers for Category entity."""
import strawberry
from typing import List, Optional

from .types import CategoryType
from repositories import categories_repo


@strawberry.type
class CategoryQuery:
    @strawberry.field(description="Lista de categorías con subcategorías")
    async def categories(self) -> List[CategoryType]:
        categories = await categories_repo.get_all()
        return [CategoryType(**c.model_dump()) for c in categories]

    @strawberry.field(description="Obtener categoría por ID")
    async def category(self, id: str) -> Optional[CategoryType]:
        category = await categories_repo.get_by_id(id)
        return CategoryType(**category.model_dump()) if category else None
