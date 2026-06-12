"""GraphQL input types for ad campaign mutations."""

from typing import Optional

import strawberry


@strawberry.input
class CreateAdCampaignInput:
    businessId: str
    branchId: str
    name: str
    placement: str  # "destacado" | "oferta"
    durationDays: int
    creativeImagePath: str  # S3 path of the exported creative photo


@strawberry.input
class UpdateAdCampaignInput:
    name: Optional[str] = None
    durationDays: Optional[int] = None
    creativeImagePath: Optional[str] = None
