"""Modelos del registro de socios: quién pide vender en Llegó o ser mensajero.

Una persona entra en la web (/negocios), inicia sesión con Google o Apple y deja una
solicitud de tipo ``business`` (quiere vender) o ``courier`` (quiere repartir). El
equipo la gestiona desde el Panel Admin: llama al solicitante, la marca como
contactada y la aprueba o la rechaza.

Aprobar da acceso (services/partner_requests_service.py):

- ``courier``: el usuario queda como mensajero aprobado. La fuente de verdad es
  ``delivery_persons.approved`` (services/courier_access.py), no esta colección.
- ``business``: se aprueban los negocios pendientes del usuario y los que registre
  después nacen aprobados.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class PartnerRequestKind(str, Enum):
    """Qué pide el solicitante."""

    BUSINESS = "business"  # vender en Llegó (app de negocios)
    COURIER = "courier"  # ser mensajero (AppMensajeros)


class PartnerRequestStatus(str, Enum):
    """Ciclo de vida de una solicitud, movido desde el Panel Admin.

    pending   -> recién enviada desde la web
    contacted -> el equipo ya habló con el solicitante
    approved  -> aceptada: da acceso (ver el docstring del módulo)
    rejected  -> rechazada: no da acceso (y lo quita si lo tenía, en mensajeros)
    """

    PENDING = "pending"
    CONTACTED = "contacted"
    APPROVED = "approved"
    REJECTED = "rejected"


# Una solicitud "activa" es la que el equipo aún tiene que resolver. Solo puede
# haber una activa por usuario y tipo (índice único parcial sobre `active`, en
# clients/mongodb_client.py).
ACTIVE_PARTNER_REQUEST_STATUSES = frozenset(
    {PartnerRequestStatus.PENDING, PartnerRequestStatus.CONTACTED}
)


def is_active_status(status: PartnerRequestStatus) -> bool:
    """True si la solicitud sigue abierta (pendiente o contactada)."""
    return PartnerRequestStatus(status) in ACTIVE_PARTNER_REQUEST_STATUSES


class PartnerRequest(BaseModel):
    """Solicitud para vender en Llegó o ser mensajero."""

    id: PyObjectId = Field(alias="_id")
    userId: PyObjectId
    type: PartnerRequestKind
    status: PartnerRequestStatus = PartnerRequestStatus.PENDING

    # Datos de contacto que deja el solicitante. `phone` va normalizado a
    # formato internacional (utils/phone.normalize_phone): "+53XXXXXXXX" en Cuba.
    fullName: str
    phone: str
    # Email de la cuenta con la que inició sesión (no lo escribe el solicitante).
    email: Optional[str] = None
    businessName: Optional[str] = None
    municipality: Optional[str] = None
    notes: Optional[str] = None

    # Gestión interna, solo la escribe el Panel Admin.
    adminNotes: Optional[str] = None
    reviewedAt: Optional[datetime] = None
    reviewedBy: Optional[PyObjectId] = None

    # Copia de `status in (pending, contacted)`. Existe solo para el índice único
    # parcial: un partialFilterExpression con $in no funciona en MongoDB < 6.
    active: bool = True

    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
