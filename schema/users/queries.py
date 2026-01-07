"""GraphQL query resolvers for User entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import UserType
from models import users_repo
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class UserQuery:
    @strawberry.field(description="Lista de usuarios")
    async def users(self, info: Info, jwt: Optional[str] = None) -> List[UserType]:
        apply_optional_jwt(jwt, info)
        users = await users_repo.get_all()
        return [UserType(**u.model_dump(exclude={'password', 'location'})) for u in users]

    @strawberry.field(description="Obtener usuario por ID")
    async def user(self, info: Info, id: str, jwt: Optional[str] = None) -> Optional[UserType]:
        apply_optional_jwt(jwt, info)
        user = await users_repo.get_by_id(id)
        return UserType(**user.model_dump(exclude={'password', 'location'})) if user else None

    @strawberry.field(description="Buscar usuarios")
    async def search_users(
        self,
        info: Info,
        query: str,
        jwt: Optional[str] = None
    ) -> List[UserType]:
        apply_optional_jwt(jwt, info)
        users = await users_repo.search(query)
        return [UserType(**u.model_dump(exclude={'password', 'location'})) for u in users]

    @strawberry.field(description="Usuario actual desde JWT")
    async def me(self, info: Info, jwt: str) -> Optional[UserType]:
        user_id = apply_optional_jwt(jwt, info)
        if not user_id:
            return None
        user = await users_repo.get_by_id(user_id)
        return UserType(**user.model_dump(exclude={'password', 'location'})) if user else None
