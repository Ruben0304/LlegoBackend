"""Roles privilegiados vigentes, leídos de la base (M6).

El JWT dura 30 días y lleva el rol: a quien se le quitaba el rol de admin (o se le borraba
la cuenta) seguía entrando con su token hasta que caducara. `require_role` y
`apply_optional_jwt` son síncronos y tienen más de cien llamadas, así que en vez de consultar
la base en cada petición se guarda en memoria quién tiene cada rol privilegiado y se refresca
cada `INTERVALO_S` segundos (worker en clients/lifespan.py).
"""
from typing import Dict, Optional, Set

from clients.mongodb_client import get_database

ROLES_PRIVILEGIADOS = ("admin", "manager", "risk_admin")
INTERVALO_S = 60

# None hasta la primera lectura: mientras tanto se confía en el token (pruebas, arranque).
_vigentes: Optional[Dict[str, Set[str]]] = None


async def refrescar(db=None) -> None:
    """Relee de `users` quién tiene cada rol privilegiado. Si falla, se queda la lectura anterior."""
    global _vigentes
    db = db if db is not None else get_database()
    nuevos: Dict[str, Set[str]] = {rol: set() for rol in ROLES_PRIVILEGIADOS}
    cursor = db["users"].find({"role": {"$in": list(ROLES_PRIVILEGIADOS)}}, {"role": 1})
    for doc in await cursor.to_list(length=None):
        nuevos[doc["role"]].add(str(doc["_id"]))
    _vigentes = nuevos


def rol_vigente(user_id: Optional[str], rol_del_token: Optional[str]) -> Optional[str]:
    """El rol con que se atiende la petición.

    Un rol privilegiado del token solo vale si la base lo confirma; si la base le da otro rol
    privilegiado se usa ese, y si no tiene ninguno pasa a `customer`. Los demás roles
    (customer, merchant...) no dan permisos especiales y se dejan como vienen.
    """
    if rol_del_token not in ROLES_PRIVILEGIADOS or _vigentes is None:
        return rol_del_token
    uid = str(user_id)
    if uid in _vigentes[rol_del_token]:
        return rol_del_token
    for rol in ROLES_PRIVILEGIADOS:
        if uid in _vigentes[rol]:
            return rol
    return "customer"
