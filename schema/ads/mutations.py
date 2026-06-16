"""GraphQL mutations for ad campaigns."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import ad_campaigns_repo, branches_repo, businesses_repo
from services.ads_service import ads_service
from utils.graphql_auth import apply_optional_jwt, require_role

from .inputs import (
    CreateAdCampaignInput,
    UpdateAdCampaignInput,
)
from .types import AdCampaignType, campaign_to_type


async def _require_owned_campaign(info: Info, jwt: Optional[str], campaign_id: str):
    """Resolve a campaign and assert the authenticated user owns it."""
    apply_optional_jwt(jwt, info)
    user_id = info.context.get("user_id")
    if not user_id:
        raise Exception("Usuario no autenticado")
    campaign = await ad_campaigns_repo.get_by_id(campaign_id)
    if not campaign:
        raise Exception("Campaña no encontrada")
    if str(campaign.ownerId) != str(user_id):
        raise Exception("No autorizado")
    return campaign


@strawberry.type
class AdCampaignMutation:
    @strawberry.mutation(description="Crear una campaña (queda en borrador)")
    async def create_ad_campaign(
        self, info: Info, input: CreateAdCampaignInput, jwt: Optional[str] = None
    ) -> AdCampaignType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Fixed price for the chosen placement + duration.
        pricing = await ads_service.quote(input.placement, input.durationDays)

        business = await businesses_repo.get_by_id(input.businessId)
        if not business:
            raise Exception("Negocio no encontrado")
        # TODO: extend to managers via business_access; owner-only for now (billing safety).
        if str(business.ownerId) != str(user_id):
            raise Exception("No autorizado para este negocio")

        branch = await branches_repo.get_by_id(input.branchId)
        if not branch:
            raise Exception("Sucursal no encontrada")
        if str(branch.businessId) != str(business.id):
            raise Exception("La sucursal no pertenece al negocio")

        data = {
            "businessId": input.businessId,
            "branchId": input.branchId,
            "ownerId": user_id,
            "name": input.name,
            "placement": input.placement,
            "creativeImagePath": input.creativeImagePath,
            "durationDays": input.durationDays,
            "price": pricing.price,
            "currency": pricing.currency,
            "paymentStatus": "unpaid",
            "status": "draft",
            "approved": False,
            "impressions": 0,
            "clicks": 0,
        }
        created = await ad_campaigns_repo.create(data)
        return campaign_to_type(created)

    @strawberry.mutation(description="Editar una campaña (solo borrador o rechazada)")
    async def update_ad_campaign(
        self,
        info: Info,
        id: str,
        input: UpdateAdCampaignInput,
        jwt: Optional[str] = None,
    ) -> AdCampaignType:
        campaign = await _require_owned_campaign(info, jwt, id)
        if campaign.status not in ("draft", "rejected"):
            raise Exception("Solo se pueden editar campañas en borrador o rechazadas")

        updates: dict = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.creativeImagePath is not None:
            updates["creativeImagePath"] = input.creativeImagePath
        if input.durationDays is not None and input.durationDays != campaign.durationDays:
            pricing = await ads_service.quote(campaign.placement, input.durationDays)
            updates["durationDays"] = input.durationDays
            updates["price"] = pricing.price
            updates["currency"] = pricing.currency
        # Re-editing a rejected campaign returns it to draft for re-submission.
        if campaign.status == "rejected":
            updates["status"] = "draft"
            updates["rejectionReason"] = None

        updated = await ad_campaigns_repo.update(id, updates)
        return campaign_to_type(updated)

    @strawberry.mutation(description="Eliminar una campaña (no activa)")
    async def delete_ad_campaign(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> bool:
        campaign = await _require_owned_campaign(info, jwt, id)
        if campaign.status == "active":
            raise Exception("No se puede eliminar una campaña activa; pausala primero")
        return await ad_campaigns_repo.delete(id)

    @strawberry.mutation(description="Pagar una campaña y enviarla a revisión")
    async def purchase_ad_campaign(
        self,
        info: Info,
        id: str,
        payment_method_id: str,
        jwt: Optional[str] = None,
    ) -> AdCampaignType:
        campaign = await _require_owned_campaign(info, jwt, id)
        if campaign.status not in ("draft", "pending_payment"):
            raise Exception("La campaña no está en un estado pagable")
        updated = await ads_service.purchase_campaign(campaign, payment_method_id)
        return campaign_to_type(updated)

    @strawberry.mutation(description="Pausar/reanudar una campaña activa")
    async def set_ad_campaign_paused(
        self, info: Info, id: str, paused: bool, jwt: Optional[str] = None
    ) -> AdCampaignType:
        campaign = await _require_owned_campaign(info, jwt, id)
        if paused and campaign.status == "active":
            updated = await ad_campaigns_repo.update(id, {"status": "paused"})
        elif not paused and campaign.status == "paused":
            updated = await ad_campaigns_repo.update(id, {"status": "active"})
        else:
            raise Exception("Transición de pausa no válida para el estado actual")
        return campaign_to_type(updated)

    # -- Admin moderation ------------------------------------------------------

    @strawberry.mutation(
        description="[Admin/Manager] Admitir una campaña en el feed (aunque no esté pagada)"
    )
    async def approve_ad_campaign(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> AdCampaignType:
        require_role(jwt, info, ["admin", "manager"])
        campaign = await ad_campaigns_repo.get_by_id(id)
        if not campaign:
            raise Exception("Campaña no encontrada")
        if campaign.status == "ended":
            raise Exception("La campaña ya terminó")
        if not campaign.creativeImagePath:
            raise Exception("La campaña no tiene creativo (foto) para mostrar")
        updated = await ads_service.approve(campaign)
        return campaign_to_type(updated)

    @strawberry.mutation(description="[Admin/Manager] Rechazar una campaña")
    async def reject_ad_campaign(
        self, info: Info, id: str, jwt: Optional[str] = None, reason: Optional[str] = None
    ) -> AdCampaignType:
        require_role(jwt, info, ["admin", "manager"])
        campaign = await ad_campaigns_repo.get_by_id(id)
        if not campaign:
            raise Exception("Campaña no encontrada")
        updated = await ads_service.reject(campaign, reason)
        return campaign_to_type(updated)

    # -- Tracking --------------------------------------------------------------

    @strawberry.mutation(description="Registrar una impresión de campaña")
    async def track_ad_impression(self, info: Info, id: str) -> bool:
        await ad_campaigns_repo.increment_metric(id, "impressions")
        return True

    @strawberry.mutation(description="Registrar un clic de campaña")
    async def track_ad_click(self, info: Info, id: str) -> bool:
        await ad_campaigns_repo.increment_metric(id, "clicks")
        return True
