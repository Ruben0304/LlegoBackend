"""Queries del registro de socios."""

from typing import Optional

import strawberry
from strawberry.types import Info

from domain.partner_requests import PartnerRequestKind, PartnerRequestStatus
from services import partner_requests_service
from utils.graphql_auth import require_auth, require_role

from .types import (
    PartnerAccessType,
    PartnerRequestPage,
    PartnerRequestStatusEnum,
    PartnerRequestTypeEnum,
    partner_access_to_type,
    partner_request_to_type,
)


@strawberry.type
class PartnerRequestQuery:
    @strawberry.field(
        description=(
            "Acceso del usuario como mensajero y como negocio, con su última "
            "solicitud de cada tipo (web /negocios y apps)."
        )
    )
    async def my_partner_access(self, info: Info, jwt: str) -> PartnerAccessType:
        user_id = require_auth(jwt, info)
        access = await partner_requests_service.get_partner_access(
            user_id, info.context.get("user_role")
        )
        return partner_access_to_type(access)

    @strawberry.field(
        description=(
            "[Admin/Manager] Solicitudes del registro de socios, de la más nueva a "
            "la más antigua. Filtros opcionales por estado y tipo."
        )
    )
    async def admin_partner_requests(
        self,
        info: Info,
        *,
        status: Optional[PartnerRequestStatusEnum] = None,
        type: Optional[PartnerRequestTypeEnum] = None,
        limit: int = 50,
        offset: int = 0,
        jwt: str,
    ) -> PartnerRequestPage:
        require_role(jwt, info, ["admin", "manager"])

        items, total = await partner_requests_service.list_partner_requests(
            status=PartnerRequestStatus(status.value) if status else None,
            kind=PartnerRequestKind(type.value) if type else None,
            limit=limit,
            offset=offset,
        )
        return PartnerRequestPage(
            items=[partner_request_to_type(r, include_admin_fields=True) for r in items],
            total=total,
        )
