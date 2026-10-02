"""Registro de socios: solicitudes para vender en Llegó o ser mensajero.

Flujo (context.md, "Registro de socios"):

1. La persona entra en la web (/negocios), inicia sesión y envía una solicitud
   (`submitPartnerRequest`). Queda `pending`.
2. El equipo la ve en el Panel Admin (`adminPartnerRequests`), llama al
   solicitante y la marca `contacted`.
3. La aprueba o la rechaza (`adminUpdatePartnerRequest`). **Aprobar da acceso**:
   - COURIER: el usuario queda como mensajero aprobado (delivery_persons.approved,
     ver services/courier_access.py), creando su registro si no existe.
   - BUSINESS: se aprueban los negocios pendientes que ya tenga y los que
     registre después nacen aprobados (`is_merchant_approved`).
   Rechazar no da acceso; si la solicitud de mensajero estaba aprobada, se lo
   quita (approved=False).

Los ValueError de este módulo llevan el mensaje en español que ve el usuario.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from domain.partner_requests import (
    PartnerRequest,
    PartnerRequestKind,
    PartnerRequestStatus,
)
from repositories import partner_requests_repo, users_repo
from repositories.orders_repository import delivery_persons_repo
from services.business_approval import approve_pending_businesses_of_owner
from services.courier_access import has_courier_access, is_approved_courier
from utils.phone import normalize_phone

# Límites de los campos de texto libre (lo que cabe razonablemente en el panel).
MAX_NAME_LENGTH = 120
MAX_BUSINESS_NAME_LENGTH = 120
MAX_MUNICIPALITY_LENGTH = 80
MAX_NOTES_LENGTH = 1000
MAX_ADMIN_NOTES_LENGTH = 2000

INVALID_PHONE_MESSAGE = (
    "El teléfono no es válido. Escribe tu número cubano de 8 dígitos "
    "(por ejemplo 5XXXXXXX) o, si es de otro país, con su código (+1 305 555 1234)."
)

_KIND_LABELS = {
    PartnerRequestKind.BUSINESS: "vender en Llegó",
    PartnerRequestKind.COURIER: "ser mensajero",
}

# Una solicitud resuelta (aprobada o rechazada) no vuelve a abrirse: se aprueba o
# se rechaza. Volver a pendiente/contactada dejaría dos solicitudes activas si el
# usuario ya envió otra, y no deshace el acceso que dio aprobarla.
_RESOLVED = frozenset({PartnerRequestStatus.APPROVED, PartnerRequestStatus.REJECTED})


@dataclass
class PartnerAccess:
    """Lo que devuelve `myPartnerAccess`."""

    courier_approved: bool
    merchant_approved: bool
    latest_courier_request: Optional[PartnerRequest]
    latest_business_request: Optional[PartnerRequest]


def _clean_text(value: Optional[str], max_length: int, label: str) -> Optional[str]:
    """Texto sin espacios sobrantes, None si queda vacío; error si es demasiado largo."""
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"{label} no puede tener más de {max_length} caracteres")
    return text


async def submit_partner_request(
    user_id: str,
    kind: PartnerRequestKind,
    full_name: str,
    phone: str,
    business_name: Optional[str] = None,
    municipality: Optional[str] = None,
    notes: Optional[str] = None,
) -> PartnerRequest:
    """Crea la solicitud del usuario (estado `pending`).

    Valida y normaliza el teléfono (utils/phone.normalize_phone: 8 dígitos ->
    "+53XXXXXXXX"), guarda el email de la cuenta e impide tener dos solicitudes
    activas (pendiente/contactada) del mismo tipo, o pedir un acceso que ya tiene.
    """
    kind = PartnerRequestKind(kind)

    name = _clean_text(full_name, MAX_NAME_LENGTH, "El nombre")
    if not name or len(name) < 2:
        raise ValueError("Escribe tu nombre completo")

    if not (phone or "").strip():
        raise ValueError("El teléfono es obligatorio")
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        raise ValueError(INVALID_PHONE_MESSAGE)

    business = _clean_text(business_name, MAX_BUSINESS_NAME_LENGTH, "El nombre del negocio")
    if kind == PartnerRequestKind.COURIER:
        # Un mensajero no registra negocio: no se guarda aunque llegue.
        business = None
    place = _clean_text(municipality, MAX_MUNICIPALITY_LENGTH, "El municipio")
    extra = _clean_text(notes, MAX_NOTES_LENGTH, "Las notas")

    user = await users_repo.get_by_id(user_id)
    if not user:
        raise ValueError("Usuario no encontrado")

    active = await partner_requests_repo.get_active_for_user(user_id, kind)
    if active:
        raise ValueError(_already_active_message(kind, active.phone))

    if kind == PartnerRequestKind.COURIER:
        if is_approved_courier(await delivery_persons_repo.get_by_user_id(user_id)):
            raise ValueError("Tu cuenta ya está aprobada como mensajero")
    elif await is_merchant_approved(user_id):
        raise ValueError("Tu cuenta ya está aprobada para vender en Llegó")

    try:
        return await partner_requests_repo.create(
            {
                "userId": user_id,
                "type": kind,
                "fullName": name,
                "phone": normalized_phone,
                "email": getattr(user, "email", None),
                "businessName": business,
                "municipality": place,
                "notes": extra,
            }
        )
    except DuplicateKeyError:
        # Doble envío simultáneo: el índice único parcial frenó el segundo.
        raise ValueError(_already_active_message(kind, normalized_phone))


def _already_active_message(kind: PartnerRequestKind, phone: str) -> str:
    return (
        f"Ya tienes una solicitud pendiente para {_KIND_LABELS[kind]}. "
        f"Nos comunicaremos contigo al {phone}."
    )


async def is_merchant_approved(user_id: str) -> bool:
    """True si el usuario tiene una solicitud BUSINESS aprobada.

    Es lo que hace que `registerBusiness` cree el negocio ya aprobado. Rechazar
    esa solicitud lo quita. Los dueños de negocios aprobados antes del registro
    de socios no cuentan: siguen pasando por la aprobación de cada negocio, como
    hasta ahora.
    """
    return await partner_requests_repo.exists_with_status(
        user_id, PartnerRequestKind.BUSINESS, PartnerRequestStatus.APPROVED
    )


async def get_partner_access(user_id: str, role: Optional[str]) -> PartnerAccess:
    """Estado de acceso del usuario y su última solicitud de cada tipo.

    `courier_approved` es el mismo criterio que aplican las operaciones de chofer
    (services/courier_access.py), rol admin/manager incluido.
    """
    return PartnerAccess(
        courier_approved=await has_courier_access(user_id, role),
        merchant_approved=await is_merchant_approved(user_id),
        latest_courier_request=await partner_requests_repo.get_latest_for_user(
            user_id, PartnerRequestKind.COURIER
        ),
        latest_business_request=await partner_requests_repo.get_latest_for_user(
            user_id, PartnerRequestKind.BUSINESS
        ),
    )


async def list_partner_requests(
    status: Optional[PartnerRequestStatus],
    kind: Optional[PartnerRequestKind],
    limit: int,
    offset: int,
) -> Tuple[List[PartnerRequest], int]:
    """Página de solicitudes para el Panel Admin, de la más nueva a la más antigua."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    items = await partner_requests_repo.list_requests(
        status=status, kind=kind, limit=limit, skip=offset
    )
    total = await partner_requests_repo.count_requests(status=status, kind=kind)
    return items, total


async def review_partner_request(
    request_id: str,
    status: PartnerRequestStatus,
    reviewer_id: str,
    admin_notes: Optional[str] = None,
) -> PartnerRequest:
    """Cambia el estado de una solicitud desde el Panel Admin y aplica el acceso.

    - `admin_notes` None deja las notas como estaban; "" las borra.
    - APPROVED da acceso (ver el docstring del módulo). Repetir la aprobación lo
      vuelve a aplicar (idempotente), útil si la primera vez falló a medias.
    - REJECTED de una solicitud COURIER que estaba aprobada quita el acceso.
    - Una solicitud aprobada o rechazada no vuelve a pendiente ni a contactada.

    El acceso se aplica antes de guardar el estado: si falla, la solicitud no
    cambia y basta con repetir la acción.
    """
    status = PartnerRequestStatus(status)
    request = await partner_requests_repo.get_by_id(request_id)
    if not request:
        raise ValueError("Solicitud no encontrada")

    previous = PartnerRequestStatus(request.status)
    if previous in _RESOLVED and status not in _RESOLVED:
        raise ValueError(
            "Una solicitud aprobada o rechazada no puede volver a pendiente ni a "
            "contactada. Apruébala o recházala."
        )

    update_notes = admin_notes is not None
    notes = None
    if update_notes:
        notes = _clean_text(admin_notes, MAX_ADMIN_NOTES_LENGTH, "Las notas internas")

    user_id = str(request.userId)
    kind = PartnerRequestKind(request.type)
    if status == PartnerRequestStatus.APPROVED:
        await _grant_access(request, user_id, kind)
    elif (
        status == PartnerRequestStatus.REJECTED
        and previous == PartnerRequestStatus.APPROVED
        and kind == PartnerRequestKind.COURIER
    ):
        await delivery_persons_repo.revoke_user(user_id)

    updated = await partner_requests_repo.update_status(
        request_id,
        status,
        reviewed_by=reviewer_id,
        expected_status=previous,
        admin_notes=notes,
        update_admin_notes=update_notes,
    )
    if not updated:
        raise ValueError(
            "La solicitud cambió mientras la revisabas. Recarga e inténtalo de nuevo."
        )
    return updated


async def _grant_access(
    request: PartnerRequest, user_id: str, kind: PartnerRequestKind
) -> None:
    if kind == PartnerRequestKind.COURIER:
        await delivery_persons_repo.approve_user(
            user_id, name=request.fullName, phone=request.phone
        )
    else:
        await approve_pending_businesses_of_owner(user_id)
