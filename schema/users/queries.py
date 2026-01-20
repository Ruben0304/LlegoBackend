"""GraphQL query resolvers for User entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import UserType
from models import users_repo
from utils.graphql_auth import apply_optional_jwt, require_auth, require_role


@strawberry.type
class UserQuery:
    @strawberry.field(description="Lista de usuarios (requiere rol admin o manager)")
    async def users(self, info: Info, jwt: str) -> List[UserType]:
        """List all users. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        users = await users_repo.get_all()
        return [UserType(**{**u.model_dump(exclude={'password', 'location'}), '_wallet': u.wallet, '_wallet_status': u.walletStatus}) for u in users]

    @strawberry.field(description="Obtener usuario por ID (requiere rol admin o manager)")
    async def user(self, info: Info, id: str, jwt: str) -> Optional[UserType]:
        """Get user by ID. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        user = await users_repo.get_by_id(id)
        return UserType(**{**user.model_dump(exclude={'password', 'location'}), '_wallet': user.wallet, '_wallet_status': user.walletStatus}) if user else None

    @strawberry.field(description="Buscar usuarios (requiere rol admin o manager)")
    async def search_users(
        self,
        info: Info,
        query: str,
        jwt: str
    ) -> List[UserType]:
        """Search users. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        users = await users_repo.search(query)
        return [UserType(**{**u.model_dump(exclude={'password', 'location'}), '_wallet': u.wallet, '_wallet_status': u.walletStatus}) for u in users]

    @strawberry.field(description="Usuario actual desde JWT")
    async def me(self, info: Info, jwt: str) -> Optional[UserType]:
        """Get current authenticated user."""
        user_id = require_auth(jwt, info)
        user = await users_repo.get_by_id(user_id)
        return UserType(**{**user.model_dump(exclude={'password', 'location'}), '_wallet': user.wallet, '_wallet_status': user.walletStatus}) if user else None
