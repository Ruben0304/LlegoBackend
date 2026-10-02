"""Registro de socios: solicitudes para vender en Llegó o ser mensajero."""
from .inputs import SubmitPartnerRequestInput
from .mutations import PartnerRequestMutation
from .queries import PartnerRequestQuery
from .types import (
    PartnerAccessType,
    PartnerRequestPage,
    PartnerRequestStatusEnum,
    PartnerRequestType,
    PartnerRequestTypeEnum,
)

__all__ = [
    "PartnerAccessType",
    "PartnerRequestMutation",
    "PartnerRequestPage",
    "PartnerRequestQuery",
    "PartnerRequestStatusEnum",
    "PartnerRequestType",
    "PartnerRequestTypeEnum",
    "SubmitPartnerRequestInput",
]
