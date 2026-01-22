"""GraphQL query resolvers for invitations and business access."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from repositories import branch_invitations_repo, business_access_repo, businesses_repo
from utils.graphql_auth import apply_optional_jwt, require_auth
from .types import BranchInvitationType, BusinessAccessType, invitation_to_type, business_access_to_type


@strawberry.type
class InvitationQuery:
    @strawberry.field(description="Vista previa de una invitacion por codigo")
    async def invitation_by_code(
        self,
        info: Info,
        code: str,
        jwt: Optional[str] = None
    ) -> Optional[BranchInvitationType]:
        apply_optional_jwt(jwt, info)
        invitation = await branch_invitations_repo.get_by_code(code)
        return invitation_to_type(invitation) if invitation else None

    @strawberry.field(description="Todas las invitaciones de un negocio (dueno)")
    async def invitations_by_business(
        self,
        info: Info,
        business_id: str,
        jwt: str
    ) -> List[BranchInvitationType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise Exception("Negocio no encontrado")
        if business.ownerId != user_id:
            raise Exception("No autorizado para ver invitaciones de este negocio")

        invitations = await branch_invitations_repo.get_by_business(business_id)
        return [invitation_to_type(invitation) for invitation in invitations]

    @strawberry.field(description="Invitaciones activas de un negocio (dueno)")
    async def active_invitations_by_business(
        self,
        info: Info,
        business_id: str,
        jwt: str
    ) -> List[BranchInvitationType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise Exception("Negocio no encontrado")
        if business.ownerId != user_id:
            raise Exception("No autorizado para ver invitaciones de este negocio")

        invitations = await branch_invitations_repo.get_active_by_business(business_id)
        return [invitation_to_type(invitation) for invitation in invitations]

    @strawberry.field(description="Accesos a negocio por negocio (dueno)")
    async def business_access_by_business(
        self,
        info: Info,
        business_id: str,
        jwt: str
    ) -> List[BusinessAccessType]:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise Exception("Negocio no encontrado")
        if business.ownerId != user_id:
            raise Exception("No autorizado para ver accesos de este negocio")

        accesses = await business_access_repo.get_by_business(business_id)
        return [business_access_to_type(access) for access in accesses]

    @strawberry.field(description="Mis accesos a negocios")
    async def my_business_access(
        self,
        info: Info,
        jwt: str
    ) -> List[BusinessAccessType]:
        user_id = require_auth(jwt, info)
        accesses = await business_access_repo.get_by_user(user_id)
        return [business_access_to_type(access) for access in accesses]
