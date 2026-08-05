"""Promo GraphQL schema module."""
from .types import PromoRequestType, PromoRequestPage
from .queries import PromoQuery
from .mutations import PromoMutation

__all__ = [
    "PromoRequestType",
    "PromoRequestPage",
    "PromoQuery",
    "PromoMutation",
]
