"""GraphQL type definitions for invitations and business access."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

import strawberry
from strawberry.types import Info

from repositories import (
    branch_invitations_repo,
    branches_repo,
    businesses_repo,
    users_repo,
)
from schema.wallet.types import WalletBalanceType


@strawberry.enum
class InvitationType(Enum):
    BRANCH = "branch"
    BUSINESS = "business"


@strawberry.enum
class InvitationStatus(Enum):
    PENDING = "pending"
    USED = "used"
    REVOKED = "revoked"


def _user_to_type(user):
    from schema.users.types import UserType

    return UserType(
        **{
            **user.model_dump(
                exclude={"password", "location", "wallet", "walletStatus"}
            ),
            "wallet": WalletBalanceType(
                local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
            ),
            "walletStatus": user.walletStatus,
        }
    )


def _branch_to_type(branch):
    from schema.branches.types import BranchType
    from schema.branches.utils import branch_to_dict

    return BranchType(**branch_to_dict(branch))


@strawberry.type
class BranchInvitationType:
    id: str
    code: str
    invitationType: InvitationType
    branchId: Optional[str]
    businessId: str
    accessDurationDays: Optional[int]
    createdBy: str
    createdAt: datetime
    status: InvitationStatus
    usedBy: Optional[str]
    usedAt: Optional[datetime]
    accessExpiresAt: Optional[datetime]

    @strawberry.field(description="Sucursal asociada a la invitacion")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        if not self.branchId:
            return None

        branch = await branches_repo.get_by_id(self.branchId)
        return _branch_to_type(branch) if branch else None

    @strawberry.field(description="Negocio asociado a la invitacion")
    async def business(
        self, info: Info
    ) -> Optional[
        Annotated["BusinessType", strawberry.lazy("schema.businesses.types")]
    ]:
        from schema.businesses.types import BusinessType

        business = await businesses_repo.get_by_id(self.businessId)
        return BusinessType(**business.model_dump()) if business else None

    @strawberry.field(description="Creador de la invitacion")
    async def creator(
        self, info: Info
    ) -> Optional[Annotated["UserType", strawberry.lazy("schema.users.types")]]:
        user_id = info.context.get("user_id")
        if not user_id:
            return None

        business = await businesses_repo.get_by_id(self.businessId)
        if not business:
            return None

        if business.ownerId != user_id and user_id != self.usedBy:
            return None

        user = await users_repo.get_by_id(self.createdBy)
        return _user_to_type(user) if user else None

    @strawberry.field(description="Usuario que canjeo la invitacion")
    async def redeemer(
        self, info: Info
    ) -> Optional[Annotated["UserType", strawberry.lazy("schema.users.types")]]:
        if not self.usedBy:
            return None

        user_id = info.context.get("user_id")
        if not user_id:
            return None

        business = await businesses_repo.get_by_id(self.businessId)
        if not business:
            return None

        if business.ownerId != user_id and user_id != self.usedBy:
            return None

        user = await users_repo.get_by_id(self.usedBy)
        return _user_to_type(user) if user else None

    @strawberry.field(description="Si el codigo esta disponible para usar")
    def is_usable(self) -> bool:
        return self.status == InvitationStatus.PENDING

    @strawberry.field(description="Estado del acceso otorgado por la invitacion")
    def access_status(self) -> str:
        if self.status == InvitationStatus.PENDING:
            return "pending"
        if self.status == InvitationStatus.REVOKED:
            return "expired"
        if self.accessExpiresAt and self.accessExpiresAt <= datetime.utcnow():
            return "expired"
        return "active"


@strawberry.type
class BusinessAccessType:
    id: str
    userId: str
    businessId: str
    invitationId: str
    grantedAt: datetime
    expiresAt: Optional[datetime]
    isActive: bool
    revokedAt: Optional[datetime]
    revokedBy: Optional[str]

    @strawberry.field(description="Usuario con acceso al negocio")
    async def user(
        self, info: Info
    ) -> Optional[Annotated["UserType", strawberry.lazy("schema.users.types")]]:
        user_id = info.context.get("user_id")
        if not user_id:
            return None

        business = await businesses_repo.get_by_id(self.businessId)
        if not business:
            return None

        if business.ownerId != user_id and user_id != self.userId:
            return None

        user = await users_repo.get_by_id(self.userId)
        return _user_to_type(user) if user else None

    @strawberry.field(description="Negocio asociado")
    async def business(
        self, info: Info
    ) -> Optional[
        Annotated["BusinessType", strawberry.lazy("schema.businesses.types")]
    ]:
        from schema.businesses.types import BusinessType

        business = await businesses_repo.get_by_id(self.businessId)
        return BusinessType(**business.model_dump()) if business else None

    @strawberry.field(description="Invitacion que otorgo el acceso")
    async def invitation(self, info: Info) -> Optional["BranchInvitationType"]:
        invitation = await branch_invitations_repo.get_by_id(self.invitationId)
        return invitation_to_type(invitation) if invitation else None

    @strawberry.field(description="Si el acceso ya expiro")
    def is_expired(self) -> bool:
        return bool(self.expiresAt and self.expiresAt <= datetime.utcnow())

    @strawberry.field(description="Dias restantes para expiracion (si aplica)")
    def days_until_expiration(self) -> Optional[int]:
        if not self.expiresAt:
            return None
        delta = self.expiresAt - datetime.utcnow()
        return max(delta.days, 0)


def invitation_to_type(invitation) -> BranchInvitationType:
    return BranchInvitationType(
        id=invitation.id,
        code=invitation.code,
        invitationType=InvitationType(invitation.invitationType),
        branchId=invitation.branchId,
        businessId=invitation.businessId,
        accessDurationDays=invitation.accessDurationDays,
        createdBy=invitation.createdBy,
        createdAt=invitation.createdAt,
        status=InvitationStatus(invitation.status),
        usedBy=invitation.usedBy,
        usedAt=invitation.usedAt,
        accessExpiresAt=invitation.accessExpiresAt,
    )


def business_access_to_type(access) -> BusinessAccessType:
    return BusinessAccessType(
        id=access.id,
        userId=access.userId,
        businessId=access.businessId,
        invitationId=access.invitationId,
        grantedAt=access.grantedAt,
        expiresAt=access.expiresAt,
        isActive=access.isActive,
        revokedAt=access.revokedAt,
        revokedBy=access.revokedBy,
    )
