"""Pydantic models for the advertising / paid-visibility feature.

A business buys an *ad campaign* to appear in the customer feed in one of two
placements:

- ``destacado``  -> "Negocios Destacados" carousel near the top of the feed.
- ``oferta``     -> "Ofertas" section (a promo/discount creative).

The business *designs its own creative* inside LlegoBusiness. Because the
merchant app (Compose) and the customer app (SwiftUI) are different rendering
engines, the creative is stored as a render-agnostic declarative spec
(:class:`CreativeSpec`) that both apps paint natively. The only binary asset is
an optional image layer, stored via the existing S3 pipeline.

Billing is a *fixed fee* per (placement, duration) read from :class:`AdPricing`,
payable from the branch wallet, by CUP transfer, or by Stripe — like an order.
"""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId

# =============================================================================
# Allowed value sets (stored as plain strings for Mongo compatibility)
# =============================================================================

# Where the campaign shows in the feed.
CAMPAIGN_PLACEMENTS = ("destacado", "oferta")

# Campaign lifecycle.
#   draft           -> created, still editable, not paid
#   pending_payment -> awaiting payment confirmation (transfer proof / stripe)
#   pending_review  -> paid, awaiting admin moderation
#   active          -> approved and within [startAt, endAt]; eligible for feed
#   paused          -> temporarily hidden by the business
#   rejected        -> moderation rejected (see rejectionReason)
#   ended           -> past endAt
CAMPAIGN_STATUSES = (
    "draft",
    "pending_payment",
    "pending_review",
    "active",
    "paused",
    "rejected",
    "ended",
)

# Payment state, decoupled from moderation.
PAYMENT_STATUSES = ("unpaid", "pending_proof", "paid", "failed", "refunded")

# Shared animation presets — each app implements these natively so the motion
# looks the same on both platforms. Keep in sync with the iOS/Compose enums.
ANIMATION_PRESETS = (
    "none",
    "fade_in",
    "slide_in",
    "pulse",
    "gradient_shift",
    "shine",
)

CREATIVE_BACKGROUND_TYPES = ("solid", "gradient", "image")
CREATIVE_TEXT_ROLES = ("eyebrow", "title", "subtitle", "cta_label")
CREATIVE_TEXT_SIZES = ("sm", "md", "lg", "xl")
CREATIVE_TEXT_WEIGHTS = ("regular", "medium", "bold")
CREATIVE_BADGE_STYLES = ("flash", "discount", "new", "offer")
CREATIVE_ASPECT_RATIOS = ("wide", "square")


# =============================================================================
# Creative spec (the declarative, render-agnostic design)
# =============================================================================


class CreativeBackground(BaseModel):
    """Background layer of the creative."""

    type: str = "gradient"  # one of CREATIVE_BACKGROUND_TYPES
    colors: List[str] = Field(default_factory=lambda: ["#023133", "#0A5C3F"])  # hex
    angle: int = 45  # gradient angle in degrees
    imagePath: Optional[str] = None  # S3 path when type == "image"


class CreativeText(BaseModel):
    """A single text layer of the creative."""

    role: str  # one of CREATIVE_TEXT_ROLES
    value: str
    color: str = "#FFFFFF"
    size: str = "md"  # one of CREATIVE_TEXT_SIZES
    weight: str = "regular"  # one of CREATIVE_TEXT_WEIGHTS


class CreativeBadge(BaseModel):
    """Optional corner badge (e.g. "OFERTA", "-30%")."""

    text: str
    style: str = "offer"  # one of CREATIVE_BADGE_STYLES


class CreativeCTA(BaseModel):
    """Optional call-to-action and where it points."""

    label: str = "Ver tienda"
    deeplink: Optional[str] = None  # e.g. "llego://branch/<id>"


class CreativeSpec(BaseModel):
    """The full declarative creative both apps render natively."""

    aspectRatio: str = "wide"  # one of CREATIVE_ASPECT_RATIOS
    background: CreativeBackground = Field(default_factory=CreativeBackground)
    texts: List[CreativeText] = Field(default_factory=list)
    badge: Optional[CreativeBadge] = None
    cta: Optional[CreativeCTA] = None
    animationPreset: str = "none"  # one of ANIMATION_PRESETS


# =============================================================================
# Campaign
# =============================================================================


class AdCampaign(BaseModel):
    """A paid feed-visibility campaign owned by a business."""

    id: PyObjectId = Field(alias="_id")
    businessId: PyObjectId
    branchId: PyObjectId
    ownerId: PyObjectId  # user that created/owns the campaign (for auth checks)

    name: str  # internal name shown to the business
    placement: str  # one of CAMPAIGN_PLACEMENTS
    creative: CreativeSpec

    # Scheduling
    durationDays: int = 7
    startAt: Optional[datetime] = None
    endAt: Optional[datetime] = None

    # Billing (fixed fee)
    price: float = 0.0
    currency: str = "usd"  # "usd" or "local"
    paymentMethodId: Optional[str] = None
    paymentStatus: str = "unpaid"  # one of PAYMENT_STATUSES
    paymentRef: Optional[str] = None  # wallet tx id / stripe intent / proof path

    # Lifecycle & moderation
    status: str = "draft"  # one of CAMPAIGN_STATUSES
    rejectionReason: Optional[str] = None
    approvedAt: Optional[datetime] = None
    rejectedAt: Optional[datetime] = None

    # Metrics
    impressions: int = 0
    clicks: int = 0

    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


# =============================================================================
# Pricing (configurable, no code change to adjust fees)
# =============================================================================


class AdPricing(BaseModel):
    """Fixed price for a (placement, durationDays) combination."""

    id: PyObjectId = Field(alias="_id")
    placement: str  # one of CAMPAIGN_PLACEMENTS
    durationDays: int  # 7, 14, 30, ...
    price: float
    currency: str = "usd"  # "usd" or "local"
    label: Optional[str] = None  # e.g. "Destacado — 1 semana"
    isActive: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
