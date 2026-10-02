"""Inputs GraphQL del registro de socios."""

from typing import Optional

import strawberry

from .types import PartnerRequestTypeEnum


@strawberry.input(description="Solicitud para vender en Llegó o ser mensajero")
class SubmitPartnerRequestInput:
    type: PartnerRequestTypeEnum
    fullName: str
    # Cubano de 8 dígitos ("5XXXXXXX", se guarda "+53XXXXXXXX") o con código de país.
    phone: str
    businessName: Optional[str] = None
    municipality: Optional[str] = None
    notes: Optional[str] = None
