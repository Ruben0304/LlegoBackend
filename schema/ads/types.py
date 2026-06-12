"""GraphQL types for ad campaigns + converters from domain models."""

from datetime import datetime
from typing import List, Optional

import strawberry
from strawberry.types import Info

from domain.ads import AdCampaign, AdPricing, CreativeSpec
from utils.s3 import get_public_url


# =============================================================================
# Creative spec (declarative; both apps render it natively)
# =============================================================================


@strawberry.type
class CreativeBackgroundType:
    type: str
    colors: List[str]
    angle: int
    imagePath: Optional[str] = None

    @strawberry.field(description="Presigned URL of the background image (if any)")
    def image_url(self) -> Optional[str]:
        return get_public_url(self.imagePath) if self.imagePath else None


@strawberry.type
class CreativeTextType:
    role: str
    value: str
    color: str
    size: str
    weight: str


@strawberry.type
class CreativeBadgeType:
    text: str
    style: str


@strawberry.type
class CreativeCTAType:
    label: str
    deeplink: Optional[str] = None


@strawberry.type
class CreativeSpecType:
    aspectRatio: str
    background: CreativeBackgroundType
    texts: List[CreativeTextType]
    animationPreset: str
    badge: Optional[CreativeBadgeType] = None
    cta: Optional[CreativeCTAType] = None


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
    creative: CreativeSpecType
    durationDays: int
    price: float
    currency: str
    paymentStatus: str
    status: str
    impressions: int
    clicks: int
    createdAt: datetime
    startAt: Optional[datetime] = None
    endAt: Optional[datetime] = None
    paymentMethodId: Optional[str] = None
    rejectionReason: Optional[str] = None
    approvedAt: Optional[datetime] = None
    rejectedAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


# =============================================================================
# Converters (domain -> GraphQL)
# =============================================================================


def creative_to_type(spec: CreativeSpec) -> CreativeSpecType:
    return CreativeSpecType(
        aspectRatio=spec.aspectRatio,
        background=CreativeBackgroundType(
            type=spec.background.type,
            colors=list(spec.background.colors),
            angle=spec.background.angle,
            imagePath=spec.background.imagePath,
        ),
        texts=[
            CreativeTextType(
                role=t.role, value=t.value, color=t.color, size=t.size, weight=t.weight
            )
            for t in spec.texts
        ],
        animationPreset=spec.animationPreset,
        badge=CreativeBadgeType(text=spec.badge.text, style=spec.badge.style)
        if spec.badge
        else None,
        cta=CreativeCTAType(label=spec.cta.label, deeplink=spec.cta.deeplink)
        if spec.cta
        else None,
    )


def campaign_to_type(c: AdCampaign) -> AdCampaignType:
    return AdCampaignType(
        id=str(c.id),
        businessId=str(c.businessId),
        branchId=str(c.branchId),
        name=c.name,
        placement=c.placement,
        creative=creative_to_type(c.creative),
        durationDays=c.durationDays,
        price=c.price,
        currency=c.currency,
        paymentStatus=c.paymentStatus,
        status=c.status,
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
