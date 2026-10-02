"""Tipos GraphQL de los banners de plataforma."""

from datetime import datetime
from typing import List, Optional

import strawberry

from domain.platform_banners import PlatformBanner
from services.platform_banners import banner_action_url
from utils.s3 import get_public_url


@strawberry.type(description="Banner promocional de la plataforma (imagen 16:9) creado por Llego")
class PlatformBannerType:
    id: str
    imagePath: str
    title: Optional[str]
    link: Optional[str]
    whatsapp: Optional[str]
    branchId: Optional[str]
    appTarget: str
    order: int
    isActive: bool
    startAt: Optional[datetime]
    endAt: Optional[datetime]
    createdAt: datetime

    @strawberry.field(description="URL pública (firmada, expira ~1h) de la imagen")
    def image_url(self) -> str:
        return get_public_url(self.imagePath)

    @strawberry.field(
        description=(
            "URL a abrir al tocar: https://wa.me/<numero> si hay whatsapp, si no el "
            "link. Null si no hay acción externa."
        )
    )
    def action_url(self) -> Optional[str]:
        return banner_action_url(self.whatsapp, self.link)


def platform_banner_to_type(banner: PlatformBanner) -> PlatformBannerType:
    return PlatformBannerType(
        id=str(banner.id),
        imagePath=banner.imagePath,
        title=banner.title,
        link=banner.link,
        whatsapp=banner.whatsapp,
        branchId=str(banner.branchId) if banner.branchId else None,
        appTarget=banner.appTarget,
        order=banner.order,
        isActive=banner.isActive,
        startAt=banner.startAt,
        endAt=banner.endAt,
        createdAt=banner.createdAt,
    )


def platform_banners_to_types(banners: List[PlatformBanner]) -> List[PlatformBannerType]:
    return [platform_banner_to_type(b) for b in banners]
