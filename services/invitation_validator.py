"""Invitation validation service for creation and redemption."""
from typing import Optional

from repositories import (
    branch_invitations_repo,
    businesses_repo,
    branches_repo,
    users_repo,
    business_access_repo,
)


class InvitationValidationError(Exception):
    """Raised when invitation validation fails."""


class InvitationValidator:
    """Business rules for invitation creation and redemption."""

    async def validate_for_creation(
        self,
        business_id: str,
        user_id: str,
        branch_id: Optional[str] = None
    ) -> None:
        business = await businesses_repo.get_by_id(business_id)
        if not business:
            raise InvitationValidationError("Negocio no encontrado")

        if business.ownerId != user_id:
            existing_access = await business_access_repo.get_by_user_and_business(user_id, business_id)
            if not existing_access or not existing_access.isActive:
                raise InvitationValidationError("No autorizado para crear invitaciones en este negocio")

        if branch_id:
            branch = await branches_repo.get_by_id(branch_id)
            if not branch:
                raise InvitationValidationError("Sucursal no encontrada")
            if branch.businessId != business_id:
                raise InvitationValidationError("La sucursal no pertenece a este negocio")

    async def validate_for_redemption(self, code: str, user_id: str):
        code = (code or "").strip()
        if not code:
            raise InvitationValidationError("Codigo de invitacion invalido")

        invitation = await branch_invitations_repo.get_by_code(code)
        if not invitation:
            raise InvitationValidationError("Codigo de invitacion no encontrado")

        if invitation.status != "pending":
            raise InvitationValidationError("El codigo de invitacion ya fue usado o revocado")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise InvitationValidationError("Usuario no encontrado")

        business = await businesses_repo.get_by_id(invitation.businessId)
        if not business:
            raise InvitationValidationError("Negocio no encontrado")

        if invitation.invitationType == "branch":
            if not invitation.branchId:
                raise InvitationValidationError("Invitacion de sucursal invalida")

            branch = await branches_repo.get_by_id(invitation.branchId)
            if not branch:
                raise InvitationValidationError("Sucursal no encontrada")
            if branch.businessId != invitation.businessId:
                raise InvitationValidationError("La sucursal no pertenece a este negocio")

            if user_id in (branch.managerIds or []):
                raise InvitationValidationError("Ya eres manager de esta sucursal")

            existing_access = await business_access_repo.get_by_user_and_business(
                user_id,
                invitation.businessId
            )
            if existing_access:
                raise InvitationValidationError("Ya tienes acceso al negocio completo")

        elif invitation.invitationType == "business":
            if business.ownerId == user_id or invitation.businessId in (user.businessIds or []):
                raise InvitationValidationError("Ya tienes acceso como propietario de este negocio")

            existing_access = await business_access_repo.get_by_user_and_business(
                user_id,
                invitation.businessId
            )
            if existing_access:
                # Check if the access is actually expired
                from datetime import datetime
                if existing_access.expiresAt and existing_access.expiresAt <= datetime.utcnow():
                    # Access is expired, mark it as inactive and allow new redemption
                    await business_access_repo.mark_as_expired(existing_access.id)
                else:
                    # Access is still active
                    raise InvitationValidationError("Ya tienes acceso a este negocio")
        else:
            raise InvitationValidationError("Tipo de invitacion invalido")

        return invitation


invitation_validator = InvitationValidator()
