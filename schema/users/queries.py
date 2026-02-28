"""GraphQL query resolvers for User entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import users_repo
from schema.wallet.types import WalletBalanceType
from utils.graphql_auth import apply_optional_jwt, require_auth, require_role

from .types import UserType


@strawberry.type
class UserQuery:
    @strawberry.field(description="Lista de usuarios (requiere rol admin o manager)")
    async def users(self, info: Info, jwt: str) -> List[UserType]:
        """List all users. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        users = await users_repo.get_all()
        return [
            UserType(
                **{
                    **u.model_dump(
                        mode="json",
                        exclude={
                            "password",
                            "location",
                            "wallet",
                            "walletStatus",
                            "isPro",
                            "aiConsultasLimit",
                        },
                    ),
                    "wallet": WalletBalanceType(
                        local=u.wallet.get("local", 0.0), usd=u.wallet.get("usd", 0.0)
                    ),
                    "walletStatus": u.walletStatus,
                }
            )
            for u in users
        ]

    @strawberry.field(
        description="Obtener usuario por ID (requiere rol admin o manager)"
    )
    async def user(self, info: Info, id: str, jwt: str) -> Optional[UserType]:
        """Get user by ID. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        user = await users_repo.get_by_id(id)
        if not user:
            return None
        return UserType(
            **{
                **user.model_dump(
                    mode="json",
                    exclude={
                        "password",
                        "location",
                        "wallet",
                        "walletStatus",
                        "isPro",
                        "aiConsultasLimit",
                    },
                ),
                "wallet": WalletBalanceType(
                    local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
                ),
                "walletStatus": user.walletStatus,
            }
        )

    @strawberry.field(description="Buscar usuarios (requiere autenticación)")
    async def search_users(self, info: Info, query: str, jwt: str) -> List[UserType]:
        """Search users. Requires authentication."""
        require_auth(jwt, info)
        users = await users_repo.search(query)
        return [
            UserType(
                **{
                    **u.model_dump(
                        mode="json",
                        exclude={
                            "password",
                            "location",
                            "wallet",
                            "walletStatus",
                            "isPro",
                            "aiConsultasLimit",
                        },
                    ),
                    "wallet": WalletBalanceType(
                        local=u.wallet.get("local", 0.0), usd=u.wallet.get("usd", 0.0)
                    ),
                    "walletStatus": u.walletStatus,
                }
            )
            for u in users
        ]

    @strawberry.field(description="Usuario actual desde JWT")
    async def me(self, info: Info, jwt: str) -> Optional[UserType]:
        """Get current authenticated user."""
        user_id = require_auth(jwt, info)
        user = await users_repo.get_by_id(user_id)
        if not user:
            return None
        return UserType(
            **{
                **user.model_dump(
                    mode="json",
                    exclude={
                        "password",
                        "location",
                        "wallet",
                        "walletStatus",
                        "isPro",
                        "aiConsultasLimit",
                    },
                ),
                "wallet": WalletBalanceType(
                    local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
                ),
                "walletStatus": user.walletStatus,
            }
        )
