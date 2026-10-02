"""Tipos GraphQL del registro de socios."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

import strawberry

from domain.partner_requests import PartnerRequest
from services.partner_requests_service import PartnerAccess


@strawberry.enum(description="Qué pide el solicitante")
class PartnerRequestTypeEnum(Enum):
    BUSINESS = "business"  # vender en Llegó
    COURIER = "courier"  # ser mensajero


@strawberry.enum(description="Estado de una solicitud del registro de socios")
class PartnerRequestStatusEnum(Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    APPROVED = "approved"
    REJECTED = "rejected"


@strawberry.type(description="Solicitud para vender en Llegó o ser mensajero")
class PartnerRequestType:
    id: str
    userId: str
    type: PartnerRequestTypeEnum
    status: PartnerRequestStatusEnum
    fullName: str
    phone: str
    email: Optional[str] = None
    businessName: Optional[str] = None
    municipality: Optional[str] = None
    notes: Optional[str] = None
    # Internas: solo las ve el Panel Admin (null para el propio solicitante).
    adminNotes: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    reviewedAt: Optional[datetime] = None
    reviewedBy: Optional[str] = None


@strawberry.type(description="Acceso del usuario como socio y su última solicitud de cada tipo")
class PartnerAccessType:
    courierApproved: bool
    merchantApproved: bool
    latestCourierRequest: Optional[PartnerRequestType] = None
    latestBusinessRequest: Optional[PartnerRequestType] = None


@strawberry.type(description="Página de solicitudes del registro de socios (Panel Admin)")
class PartnerRequestPage:
    items: List[PartnerRequestType]
    total: int


def partner_request_to_type(
    request: PartnerRequest, include_admin_fields: bool = False
) -> PartnerRequestType:
    """Convierte el modelo de dominio en su tipo GraphQL.

    Sin `include_admin_fields` (lo que ve el propio solicitante) no se exponen las
    notas internas del equipo ni quién la revisó.
    """
    return PartnerRequestType(
        id=str(request.id),
        userId=str(request.userId),
        type=PartnerRequestTypeEnum(request.type.value),
        status=PartnerRequestStatusEnum(request.status.value),
        fullName=request.fullName,
        phone=request.phone,
        email=request.email,
        businessName=request.businessName,
        municipality=request.municipality,
        notes=request.notes,
        adminNotes=request.adminNotes if include_admin_fields else None,
        createdAt=request.createdAt,
        updatedAt=request.updatedAt,
        reviewedAt=request.reviewedAt,
        reviewedBy=(
            str(request.reviewedBy)
            if include_admin_fields and request.reviewedBy
            else None
        ),
    )


def partner_access_to_type(access: PartnerAccess) -> PartnerAccessType:
    return PartnerAccessType(
        courierApproved=access.courier_approved,
        merchantApproved=access.merchant_approved,
        latestCourierRequest=(
            partner_request_to_type(access.latest_courier_request)
            if access.latest_courier_request
            else None
        ),
        latestBusinessRequest=(
            partner_request_to_type(access.latest_business_request)
            if access.latest_business_request
            else None
        ),
    )
