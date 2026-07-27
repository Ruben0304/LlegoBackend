"""GraphQL mutation resolvers for promo requests."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import promo_requests_repo
from utils.graphql_auth import require_auth, require_role
from utils.rate_limit import rate_limit_graphql

from .types import PromoRequestType, promo_request_to_type


@strawberry.type
class PromoMutation:
    @strawberry.mutation(
        description=(
            "Enviar una promo desde la app de cliente. Requiere al menos una "
            "foto o un video (sube el archivo antes a /upload/promo/image o "
            "/upload/promo/video y pasa aquí el path devuelto)."
        )
    )
    async def create_promo_request(
        self,
        info: Info,
        imagePath: Optional[str] = None,
        videoPath: Optional[str] = None,
        title: Optional[str] = None,
        whatsapp: Optional[str] = None,
        link: Optional[str] = None,
        lugar: Optional[str] = None,
        jwt: Optional[str] = None,
    ) -> PromoRequestType:
        user_id = require_auth(jwt, info)
        rate_limit_graphql(info, "uploads")

        if not imagePath and not videoPath:
            raise Exception("Debes adjuntar al menos una foto o un video")

        request = await promo_requests_repo.create(
            {
                "imagePath": imagePath,
                "videoPath": videoPath,
                "title": title,
                "whatsapp": whatsapp,
                "link": link,
                "lugar": lugar,
                "submittedByUserId": user_id,
            }
        )
        return promo_request_to_type(request)

    @strawberry.mutation(
        description="[Admin/Manager] Aprobar o rechazar una promo enviada"
    )
    async def review_promo_request(
        self,
        info: Info,
        id: str,
        status: str,
        rejectionReason: Optional[str] = None,
        jwt: Optional[str] = None,
    ) -> PromoRequestType:
        reviewer_id = require_role(jwt, info, ["admin", "manager"])

        if status not in ("approved", "rejected"):
            raise Exception("status debe ser 'approved' o 'rejected'")
        if status == "rejected" and not rejectionReason:
            raise Exception("Se requiere un motivo al rechazar una promo")

        updated = await promo_requests_repo.set_status(
            id,
            status,
            reviewed_by_user_id=reviewer_id,
            rejection_reason=rejectionReason if status == "rejected" else None,
        )
        if not updated:
            raise Exception("Promo no encontrada")
        return promo_request_to_type(updated)
