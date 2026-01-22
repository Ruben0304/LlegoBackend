"""GraphQL input types for invitation mutations."""
import strawberry
from typing import Optional

from .types import InvitationType


@strawberry.input
class GenerateInvitationInput:
    invitationType: InvitationType
    branchId: Optional[str] = None
    businessId: str
    accessDurationDays: Optional[int] = None


@strawberry.input
class AcceptInvitationInput:
    code: str
