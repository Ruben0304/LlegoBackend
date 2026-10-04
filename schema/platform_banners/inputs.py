"""Inputs GraphQL de los banners de plataforma (panel admin)."""

from datetime import datetime
from typing import Optional

import strawberry


@strawberry.input
class CreatePlatformBannerInput:
    """Banner nuevo. Sube antes la imagen a POST /upload/platform-banner/image."""

    imagePath: str
    title: Optional[str] = None
    link: Optional[str] = None
    whatsapp: Optional[str] = None
    branchId: Optional[str] = None
    appTarget: str = "customer"
    # Sin order, el banner va al final del carrusel de su app.
    order: Optional[int] = None
    isActive: bool = True
    startAt: Optional[datetime] = None
    endAt: Optional[datetime] = None


@strawberry.input
class UpdatePlatformBannerInput:
    """Edición parcial: solo cambia lo que se manda. Un null explícito borra
    el campo opcional (title, link, whatsapp, branchId, startAt, endAt)."""

    imagePath: Optional[str] = strawberry.UNSET
    title: Optional[str] = strawberry.UNSET
    link: Optional[str] = strawberry.UNSET
    whatsapp: Optional[str] = strawberry.UNSET
    branchId: Optional[str] = strawberry.UNSET
    appTarget: Optional[str] = strawberry.UNSET
    order: Optional[int] = strawberry.UNSET
    isActive: Optional[bool] = strawberry.UNSET
    startAt: Optional[datetime] = strawberry.UNSET
    endAt: Optional[datetime] = strawberry.UNSET
