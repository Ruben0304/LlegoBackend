"""Quién puede usar las operaciones de mensajero (AppMensajeros).

Antes bastaba con estar autenticado: la primera operación de chofer de cualquier
usuario le creaba un registro en `delivery_persons` y ya podía ver pedidos
disponibles, aceptarlos y recogerlos. Ahora hace falta ser **mensajero aprobado**:

- La fuente de verdad es `delivery_persons.approved` (domain/orders.py:DeliveryPerson).
  `True` lo pone aprobar una solicitud COURIER del registro de socios
  (services/partner_requests_service.py); `False`, rechazarla.
- Un registro sin el campo (`None`) es anterior al registro de socios: cuenta como
  aprobado, para que los mensajeros que ya trabajaban no pierdan el acceso.
- Sin registro no hay acceso, y ya no se crea uno automáticamente al primer uso.
- `admin` y `manager` de plataforma entran por su rol (pruebas y soporte). Si no
  tienen registro se les crea con `approved=False`, así que el acceso les dura lo
  que dure el rol.

Al denegar se lanza `CourierNotApprovedError`, cuyo mensaje empieza por
"COURIER_NOT_APPROVED" para que las apps lo distingan de cualquier otro error.
"""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from domain.orders import DeliveryPerson
from repositories import users_repo
from repositories.orders_repository import delivery_persons_repo

COURIER_NOT_APPROVED = "COURIER_NOT_APPROVED"
COURIER_NOT_APPROVED_MESSAGE = (
    f"{COURIER_NOT_APPROVED}: Tu cuenta aún no está aprobada como mensajero. "
    "Solicita el acceso en la web de Llegó (Negocios y mensajeros) y te "
    "contactaremos."
)

# Roles de plataforma que pueden usar las operaciones de mensajero sin aprobación.
STAFF_ROLES = frozenset({"admin", "manager"})


class CourierNotApprovedError(ValueError):
    """El usuario no puede operar como mensajero.

    Hereda de ValueError porque los resolvers de pedidos convierten los
    ValueError del servicio en errores GraphQL conservando el mensaje. Además
    lleva `extensions.code = "COURIER_NOT_APPROVED"`, que graphql-core copia al
    error GraphQL cuando se lanza sin envolver (lo hacen los resolvers, que
    llaman a `require_courier` antes de su try/except).
    """

    def __init__(self, message: str = COURIER_NOT_APPROVED_MESSAGE):
        super().__init__(message)
        self.extensions = {"code": COURIER_NOT_APPROVED}


def is_approved_courier(delivery_person: Optional[Any]) -> bool:
    """True si el registro de mensajero da acceso (aprobado o anterior al registro)."""
    if delivery_person is None:
        return False
    return getattr(delivery_person, "approved", None) is not False


def role_from_info(info: Any) -> Optional[str]:
    """Rol del JWT ya validado en el contexto GraphQL (lo rellena require_auth)."""
    context = getattr(info, "context", None)
    if isinstance(context, dict):
        return context.get("user_role")
    return getattr(context, "user_role", None)


async def has_courier_access(user_id: str, role: Optional[str]) -> bool:
    """Si el usuario puede usar las operaciones de mensajero. No crea nada."""
    if role in STAFF_ROLES:
        return True
    return is_approved_courier(await delivery_persons_repo.get_by_user_id(user_id))


async def require_courier(info: Any, user_id: str) -> DeliveryPerson:
    """Registro de mensajero de un usuario autorizado, o CourierNotApprovedError.

    Llamar después de `require_auth`, que deja el rol en el contexto.
    """
    delivery_person = await delivery_persons_repo.get_by_user_id(user_id)
    if is_approved_courier(delivery_person):
        return delivery_person

    if role_from_info(info) not in STAFF_ROLES:
        raise CourierNotApprovedError()

    if delivery_person is not None:
        return delivery_person
    return await _create_staff_record(user_id)


async def _create_staff_record(user_id: str) -> DeliveryPerson:
    """Registro para un admin/manager que usa la app de mensajeros.

    Nace con `approved=False`: el acceso se lo da el rol, no el registro.
    """
    user = await users_repo.get_by_id(user_id)
    if not user:
        raise ValueError("Usuario no encontrado")

    now = datetime.utcnow()
    staff_record = DeliveryPerson(
        _id=str(ObjectId()),
        userId=user_id,
        name=user.name or "",
        phone=user.phone,
        vehicleType=None,
        approved=False,
        createdAt=now,
        updatedAt=now,
    )
    try:
        return await delivery_persons_repo.create(staff_record)
    except DuplicateKeyError:
        # Dos peticiones a la vez: la otra lo creó primero (índice único por userId).
        existing = await delivery_persons_repo.get_by_user_id(user_id)
        if existing is None:
            raise
        return existing
