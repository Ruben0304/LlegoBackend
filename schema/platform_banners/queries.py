"""Queries GraphQL de los banners de plataforma."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories.platform_banner_repository import platform_banners_repo
from services.platform_banners import validate_app_target
from utils.graphql_auth import require_role

from .types import PlatformBannerType, platform_banners_to_types


@strawberry.type
class PlatformBannerQuery:
    @strawberry.field(description="Banners promocionales activos para el feed (público)")
    async def platform_banners(
        self, info: Info, appTarget: str = "customer"
    ) -> List[PlatformBannerType]:
        # Público a propósito: el carrusel se ve también sin sesión. Un appTarget
        # desconocido no es un error para la app, simplemente no tiene banners.
        try:
            target = validate_app_target(appTarget)
        except ValueError:
            return []
        banners = await platform_banners_repo.get_active(target)
        return platform_banners_to_types(banners)

    @strawberry.field(
        description=(
            "[Admin] Todos los banners (activos, inactivos y fuera de fecha) en el "
            "orden del carrusel, opcionalmente de una sola app"
        )
    )
    async def admin_platform_banners(
        self, info: Info, jwt: str, appTarget: Optional[str] = None
    ) -> List[PlatformBannerType]:
        require_role(jwt, info, ["admin"])
        if appTarget is not None:
            try:
                appTarget = validate_app_target(appTarget)
            except ValueError as exc:
                raise Exception(str(exc))
        banners = await platform_banners_repo.list_all(appTarget)
        return platform_banners_to_types(banners)
