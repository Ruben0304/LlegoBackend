"""Aprobación y rechazo de negocios.

Lo usan las mutations `approveBusiness`/`rejectBusiness` (schema/businesses/mutations.py)
y aprobar una solicitud BUSINESS del registro de socios
(services/partner_requests_service.py), que aprueba de golpe los negocios pendientes
del solicitante. Un solo sitio para que los dos caminos dejen el negocio y sus
sucursales igual.
"""

from datetime import datetime
from typing import List, Optional

from domain.models import Business
from repositories import branches_repo, businesses_repo


async def approve_business(business_id: str) -> Optional[Business]:
    """Aprueba el negocio, lo activa y reactiva sus sucursales.

    Devuelve el negocio actualizado, o None si no existe.
    """
    updated = await businesses_repo.update(
        business_id,
        {
            "approvalStatus": "approved",
            "isActive": True,
            "rejectionReason": None,
            "approvedAt": datetime.now(),
            "rejectedAt": None,
        },
    )
    if not updated:
        return None

    # Reactivar las sucursales del negocio (un rechazo previo las desactiva)
    branches = await branches_repo.get_by_business(business_id)
    for branch in branches:
        if not branch.isActive:
            await branches_repo.update(str(branch.id), {"isActive": True})
    return updated


async def reject_business(
    business_id: str, reason: Optional[str] = None
) -> Optional[Business]:
    """Rechaza el negocio y desactiva sus sucursales. None si no existe."""
    updated = await businesses_repo.update(
        business_id,
        {
            "approvalStatus": "rejected",
            "isActive": False,
            "rejectionReason": reason,
            "rejectedAt": datetime.now(),
            "approvedAt": None,
        },
    )
    if not updated:
        return None

    # Desactivar las sucursales para que dejen de exponerse (sync, búsqueda, etc.)
    branches = await branches_repo.get_by_business(business_id)
    for branch in branches:
        if branch.isActive:
            await branches_repo.update(str(branch.id), {"isActive": False})
    return updated


async def approve_pending_businesses_of_owner(owner_id: str) -> List[Business]:
    """Aprueba todos los negocios del usuario que siguen en `pending`.

    Los rechazados no se tocan: rechazar un negocio es una decisión explícita que
    aprobar la solicitud de socio no debe deshacer.
    """
    approved: List[Business] = []
    for business in await businesses_repo.get_by_owner(owner_id):
        if business.approvalStatus != "pending":
            continue
        updated = await approve_business(str(business.id))
        if updated:
            approved.append(updated)
    return approved
