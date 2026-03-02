"""GraphQL query resolvers for Showcase entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import showcases_repo
from utils.graphql_auth import apply_optional_jwt

from .types import ShowcaseType, showcase_to_type


@strawberry.type
class ShowcaseQuery:
    @strawberry.field(description="Obtener vitrina por ID")
    async def showcase(
        self, info: Info, showcase_id: str, jwt: Optional[str] = None
    ) -> Optional[ShowcaseType]:
        apply_optional_jwt(jwt, info)
        showcase = await showcases_repo.get_by_id(showcase_id)
        return showcase_to_type(showcase) if showcase else None

    @strawberry.field(description="Obtener vitrinas por sucursal")
    async def showcases_by_branch(
        self,
        info: Info,
        branch_id: str,
        active_only: bool = True,
        jwt: Optional[str] = None,
    ) -> List[ShowcaseType]:
        apply_optional_jwt(jwt, info)
        showcases = await showcases_repo.get_by_branch(branch_id, active_only)
        return [showcase_to_type(showcase) for showcase in showcases]

    @strawberry.field(description="Obtener todas las vitrinas")
    async def all_showcases(
        self, info: Info, active_only: bool = False, jwt: Optional[str] = None
    ) -> List[ShowcaseType]:
        apply_optional_jwt(jwt, info)
        showcases = await showcases_repo.get_all(active_only)
        return [showcase_to_type(showcase) for showcase in showcases]
