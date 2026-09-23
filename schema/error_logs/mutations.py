"""GraphQL mutations for the admin error inbox."""

import strawberry
from strawberry.types import Info

from repositories.error_log_repository import error_log_repo
from utils.graphql_auth import require_role


@strawberry.type
class ErrorLogMutation:
    @strawberry.mutation(
        description="(Admin) Marcar un error como resuelto (queda registrado quién lo resolvió)"
    )
    async def admin_resolve_error(self, info: Info, errorId: str, jwt: str) -> bool:
        user_id = require_role(jwt, info, ["admin", "manager"])
        return await error_log_repo.mark_resolved(errorId, resolved_by=user_id)

    @strawberry.mutation(description="(Admin) Reabrir un error marcado como resuelto")
    async def admin_unresolve_error(self, info: Info, errorId: str, jwt: str) -> bool:
        require_role(jwt, info, ["admin", "manager"])
        return await error_log_repo.mark_unresolved(errorId)
