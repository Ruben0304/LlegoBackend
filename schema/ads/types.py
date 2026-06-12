"""GraphQL types for ad campaigns + converters from domain models."""

from datetime import datetime
from typing import Optional

import strawberry

from domain.ads import AdCampaign, AdPricing
from utils.s3 import get_public_url


@strawberry.type
class AdPricingType:
    id: str
    placement: str
    durationDays: int
    price: float
    currency: str
    label: Optional[str] = None


@strawberry.type
class AdCampaignType:
    id: str
    businessId: str
    branchId: str
    name: str
    placement: str
    durationDays: int
    price: float
    currency: str
    paymentStatus: str
    status: str
    approved: bool
    impressions: int
    clicks: int
    createdAt: datetime
    creativeImagePath: Optional[str] = None
    startAt: Optional[datetime] = None
    endAt: Optional[datetime] = None
    paymentMethodId: Optional[str] = None
    rejectionReason: Optional[str] = None
    approvedAt: Optional[datetime] = None
    rejectedAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    @strawberry.field(description="Presigned URL of the exported creative photo")
    def creative_image_url(self) -> Optional[str]:
        return get_public_url(self.creativeImagePath) if self.creativeImagePath else None


# =============================================================================
# Converters (domain -> GraphQL)
# =============================================================================


def campaign_to_type(c: AdCampaign) -> AdCampaignType:
    return AdCampaignType(
        id=str(c.id),
        businessId=str(c.businessId),
        branchId=str(c.branchId),
        name=c.name,
        placement=c.placement,
        creativeImagePath=c.creativeImagePath,
        durationDays=c.durationDays,
        price=c.price,
        currency=c.currency,
        paymentStatus=c.paymentStatus,
        status=c.status,
        approved=c.approved,
        impressions=c.impressions,
        clicks=c.clicks,
        createdAt=c.createdAt,
        startAt=c.startAt,
        endAt=c.endAt,
        paymentMethodId=c.paymentMethodId,
        rejectionReason=c.rejectionReason,
        approvedAt=c.approvedAt,
        rejectedAt=c.rejectedAt,
        updatedAt=c.updatedAt,
    )


def pricing_to_type(p: AdPricing) -> AdPricingType:
    return AdPricingType(
        id=str(p.id),
        placement=p.placement,
        durationDays=p.durationDays,
        price=p.price,
        currency=p.currency,
        label=p.label,
    )
