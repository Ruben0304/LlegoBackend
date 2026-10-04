"""Mutations del registro de socios."""

from typing import Optional

import strawberry
from strawberry.types import Info

from domain.partner_requests import PartnerRequestKind, PartnerRequestStatus
from services import partner_requests_service
from utils.graphql_auth import require_auth, require_role

from .inputs import SubmitPartnerRequestInput
from .types import PartnerRequestStatusEnum, PartnerRequestType, partner_request_to_type


@strawberry.type
class PartnerRequestMutation:
    @strawberry.mutation(
        description=(
            "Enviar una solicitud para vender en Llegó o ser mensajero. Una sola "
            "solicitud pendiente/contactada por usuario y tipo."
        )
    )
    async def submit_partner_request(
        self, info: Info, input: SubmitPartnerRequestInput, jwt: str
    ) -> PartnerRequestType:
        user_id = require_auth(jwt, info)
        try:
            request = await partner_requests_service.submit_partner_request(
                user_id,
                PartnerRequestKind(input.type.value),
                full_name=input.fullName,
                phone=input.phone,
                business_name=input.businessName,
                municipality=input.municipality,
                notes=input.notes,
            )
        except ValueError as e:
            raise Exception(str(e))
        return partner_request_to_type(request)

    @strawberry.mutation(
        description=(
            "[Admin/Manager] Cambiar el estado de una solicitud del registro de "
            "socios. APPROVED da acceso: mensajero aprobado (COURIER) o negocios "
            "aprobados (BUSINESS). adminNotes null deja las notas como estaban."
        )
    )
    async def admin_update_partner_request(
        self,
        info: Info,
        *,
        id: str,
        status: PartnerRequestStatusEnum,
        adminNotes: Optional[str] = None,
        jwt: str,
    ) -> PartnerRequestType:
        reviewer_id = require_role(jwt, info, ["admin", "manager"])
        try:
            request = await partner_requests_service.review_partner_request(
                id,
                PartnerRequestStatus(status.value),
                reviewer_id=reviewer_id,
                admin_notes=adminNotes,
            )
        except ValueError as e:
            raise Exception(str(e))
        return partner_request_to_type(request, include_admin_fields=True)
