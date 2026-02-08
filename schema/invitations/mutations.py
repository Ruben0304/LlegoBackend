"""GraphQL mutations for invitation management."""
import strawberry
from typing import Optional
from datetime import datetime, timedelta
from strawberry.types import Info
from bson import ObjectId

from domain.models import BranchInvitation
from repositories import branch_invitations_repo, business_access_repo, businesses_repo
from services.invitation_validator import invitation_validator, InvitationValidationError
from services.access_manager import access_manager
from utils.invitation_codes import generate_unique_code
from utils.graphql_auth import apply_optional_jwt
from .inputs import GenerateInvitationInput, AcceptInvitationInput
from .types import BranchInvitationType, InvitationType, invitation_to_type


@strawberry.type
class InvitationMutation:
    @strawberry.mutation(description="Generar codigo de invitacion")
    async def generate_invitation_code(
        self,
        info: Info,
        input: GenerateInvitationInput,
        jwt: Optional[str] = None
    ) -> BranchInvitationType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        if input.accessDurationDays is not None:
            if input.accessDurationDays < 1 or input.accessDurationDays > 365:
                raise Exception("accessDurationDays debe estar entre 1 y 365 dias")

        if input.invitationType == InvitationType.BRANCH and not input.branchId:
            raise Exception("Debe especificar branchId para invitaciones de sucursal")
        if input.invitationType == InvitationType.BUSINESS and input.branchId:
            raise Exception("branchId no aplica para invitaciones de negocio")

        try:
            await invitation_validator.validate_for_creation(
                business_id=input.businessId,
                user_id=user_id,
                branch_id=input.branchId
            )
        except InvitationValidationError as exc:
            raise Exception(str(exc))

        code = await generate_unique_code()
        invitation = BranchInvitation(
            id=str(ObjectId()),
            code=code,
            invitationType=input.invitationType.value,
            branchId=input.branchId,
            businessId=input.businessId,
            accessDurationDays=input.accessDurationDays,
            createdBy=user_id,
            createdAt=datetime.utcnow(),
            status="pending"
        )

        await branch_invitations_repo.create(invitation)
        return invitation_to_type(invitation)

    @strawberry.mutation(description="Canjear codigo de invitacion")
    async def accept_invitation_code(
        self,
        info: Info,
        input: AcceptInvitationInput,
        jwt: Optional[str] = None
    ) -> BranchInvitationType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            invitation = await invitation_validator.validate_for_redemption(
                code=input.code,
                user_id=user_id
            )
        except InvitationValidationError as exc:
            raise Exception(str(exc))

        access_expires_at = None
        if invitation.accessDurationDays is not None:
            access_expires_at = datetime.utcnow() + timedelta(days=invitation.accessDurationDays)

        updated_invitation = await branch_invitations_repo.mark_as_used(
            invitation.code,
            user_id,
            access_expires_at
        )
        if not updated_invitation:
            raise Exception("El codigo de invitacion ya fue usado o no es valido")

        if invitation.invitationType == "branch":
            await access_manager.grant_branch_access(user_id, invitation.branchId)
        else:
            await access_manager.grant_business_access(
                user_id=user_id,
                business_id=invitation.businessId,
                invitation_id=updated_invitation.id,
                expires_at=access_expires_at
            )

        return invitation_to_type(updated_invitation)

    @strawberry.mutation(description="Revocar codigo de invitacion")
    async def revoke_invitation_code(
        self,
        info: Info,
        invitation_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        invitation = await branch_invitations_repo.get_by_id(invitation_id)
        if not invitation:
            raise Exception("Invitacion no encontrada")

        business = await businesses_repo.get_by_id(invitation.businessId)
        if not business:
            raise Exception("Negocio no encontrado")
        if business.ownerId != user_id:
            raise Exception("No autorizado para revocar invitaciones en este negocio")

        await branch_invitations_repo.revoke(invitation_id)

        if invitation.usedBy:
            if invitation.invitationType == "branch":
                active_business_access = await business_access_repo.get_by_user_and_business(
                    invitation.usedBy,
                    invitation.businessId
                )
                if not active_business_access and invitation.branchId:
                    await access_manager.revoke_branch_access(invitation.usedBy, invitation.branchId)
            else:
                access = await business_access_repo.get_by_invitation(invitation.id)
                if access and access.isActive:
                    await access_manager.revoke_business_access(access.id, revoked_by=user_id)

        return True
