"""Banners promocionales de la plataforma (`platform_banners`).

Imágenes 16:9 que crea Llego desde el panel admin y que las apps cliente
(LlegoiOS `GetPlatformBanners.graphql`, LlegoApk `ProductFeedRepository`)
muestran en el carrusel del feed principal. Son globales: no dependen de la
categoría ni del tipo de negocio.

Al tocar un banner la app abre, por este orden: la tienda (`branchId`), o la
URL externa (`actionUrl`, que se deriva de `whatsapp` o `link`).
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId

# App en la que se muestra el banner (texto plano en Mongo; la query pública
# recibe `appTarget: String` y las apps cliente piden "customer").
PLATFORM_BANNER_APP_TARGETS = ("customer", "business", "courier")


class PlatformBanner(BaseModel):
    """Banner 16:9 del carrusel del feed, gestionado por los admins."""

    id: PyObjectId = Field(alias="_id")

    imagePath: str  # path en S3 (se sube antes a /upload/platform-banner/image)
    title: Optional[str] = None
    link: Optional[str] = None  # URL externa (http/https)
    whatsapp: Optional[str] = None  # número; se expone como https://wa.me/<dígitos>
    branchId: Optional[PyObjectId] = None  # tienda a abrir al tocar

    appTarget: str = "customer"  # uno de PLATFORM_BANNER_APP_TARGETS
    order: int = 0  # posición en el carrusel (ascendente)
    isActive: bool = True

    # Ventana opcional de publicación (UTC). Fuera de ella no se muestra.
    startAt: Optional[datetime] = None
    endAt: Optional[datetime] = None

    createdByUserId: Optional[PyObjectId] = None
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
