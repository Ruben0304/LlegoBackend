"""GraphQL query resolvers for ad campaigns."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from core.config import settings
from repositories import ad_campaigns_repo
from services.ads_service import ads_service
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql

from .types import AdCampaignType, AdPricingType, campaign_to_type, pricing_to_type


@strawberry.type
class AdCampaignQuery:
    @strawberry.field(description="Tarifas fijas disponibles para campañas")
    async def ad_pricing(self, info: Info) -> List[AdPricingType]:
        rate_limit_graphql(info, "graphql")
        pricing = await ads_service.get_pricing()
        return [pricing_to_type(p) for p in pricing]

    @strawberry.field(description="Campañas del usuario autenticado")
    async def my_ad_campaigns(
        self, info: Info, jwt: Optional[str] = None
    ) -> List[AdCampaignType]:
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "graphql")
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        campaigns = await ad_campaigns_repo.get_by_owner(user_id)
        return [campaign_to_type(c) for c in campaigns]

    @strawberry.field(description="Detalle de una campaña (solo del dueño)")
    async def ad_campaign(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> Optional[AdCampaignType]:
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "graphql")
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")
        campaign = await ad_campaigns_repo.get_by_id(id)
        if not campaign:
            return None
        if str(campaign.ownerId) != str(user_id):
            raise Exception("No autorizado")
        return campaign_to_type(campaign)

    @strawberry.field(description="[Admin] Campañas pendientes de admisión")
    async def pending_ad_campaigns(
        self, info: Info, admin_key: str
    ) -> List[AdCampaignType]:
        if not settings.admin_api_key or admin_key != settings.admin_api_key:
            raise Exception("No autorizado")
        campaigns = await ad_campaigns_repo.list_pending_review()
        return [campaign_to_type(c) for c in campaigns]
