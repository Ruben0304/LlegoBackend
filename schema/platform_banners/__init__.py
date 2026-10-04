"""Banners de plataforma: carrusel 16:9 del feed gestionado desde el panel admin."""
from .types import PlatformBannerType
from .queries import PlatformBannerQuery
from .mutations import PlatformBannerMutation

__all__ = [
    "PlatformBannerType",
    "PlatformBannerQuery",
    "PlatformBannerMutation",
]
