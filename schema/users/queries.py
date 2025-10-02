"""GraphQL query resolvers for User entity."""
import strawberry
from typing import List, Optional

from .types import UserType
from models import users_repo


@strawberry.type
class UserQuery:
    @strawberry.field(description="Lista de usuarios")
    async def users(self) -> List[UserType]:
        users = await users_repo.get_all()
        return [UserType(**u.model_dump()) for u in users]

    @strawberry.field(description="Obtener usuario por ID")
    async def user(self, id: str) -> Optional[UserType]:
        user = await users_repo.get_by_id(id)
        return UserType(**user.model_dump()) if user else None

    @strawberry.field(description="Buscar usuarios")
    async def search_users(self, query: str) -> List[UserType]:
        users = await users_repo.search(query)
        return [UserType(**u.model_dump()) for u in users]
