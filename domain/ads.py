"""Pydantic models for the advertising / paid-visibility feature.

A business buys an *ad campaign* to appear in the customer feed in one of two
placements:

- ``destacado``  -> "Negocios Destacados" carousel near the top of the feed.
- ``oferta``     -> "Ofertas" section (a promo/discount creative).

The business *designs its own creative* inside LlegoBusiness with a Canva-style
canvas editor (picks a background image, drags texts and a circular branch
avatar) and **exports it as a single flat photo**. That photo is the only thing
stored (``creativeImagePath``, an S3 path); every client just shows the image.

Feed visibility is governed by a single ``approved`` boolean, decoupled from
payment: an admin may admit a campaign even if it is not paid yet.

Billing is a *fixed fee* per (placement, duration) read from :class:`AdPricing`,
payable from the branch wallet, by CUP transfer, or by Stripe — like an order.
"""

from datetime import datetime
from typing import Optional

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

    # The exported creative photo (S3 path). Optional on the model only to keep
    # parsing legacy docs alive; the API requires it on create.
    creativeImagePath: Optional[str] = None

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
    status: str = "draft"  # one of CAMPAIGN_STATUSES (payment/pause lifecycle)
    approved: bool = False  # the ONLY feed-visibility gate; set by admin
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
