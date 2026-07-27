"""Pydantic models for the *promo* feature.

A promo is submitted from the customer app by a business that is **not**
registered in Llego. The feed shows a fixed CTA banner (section ``promo``);
tapping it opens a form where the business uploads a photo **or** a video
(at least one is required) and may add a title, a WhatsApp number, a link and
a place.

Submissions are not shown in the feed: they land in ``promo_requests`` for our
internal administrative app to review, which is the only consumer of the
moderation fields below.
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field, model_validator

from .py_object_id import PyObjectId

# =============================================================================
# Allowed value sets (stored as plain strings for Mongo compatibility)
# =============================================================================

# Moderation lifecycle, driven entirely from the administrative app.
#   pending   -> submitted from the customer app, awaiting review
#   approved  -> reviewed and accepted
#   rejected  -> reviewed and declined (see rejectionReason)
PROMO_REQUEST_STATUSES = ("pending", "approved", "rejected")


# =============================================================================
# Promo request
# =============================================================================


class PromoRequest(BaseModel):
    """A promo submitted by an unregistered business from the customer app."""

    id: PyObjectId = Field(alias="_id")

    # Media (S3 paths). At least one of the two is required — see the validator.
    imagePath: Optional[str] = None
    videoPath: Optional[str] = None

    # Everything the business may optionally add.
    title: Optional[str] = None
    whatsapp: Optional[str] = None
    link: Optional[str] = None
    lugar: Optional[str] = None

    # Customer-app user that sent it, when the request was authenticated.
    submittedByUserId: Optional[PyObjectId] = None

    # Moderation, owned by the administrative app.
    status: str = "pending"  # one of PROMO_REQUEST_STATUSES
    reviewedByUserId: Optional[PyObjectId] = None
    reviewedAt: Optional[datetime] = None
    rejectionReason: Optional[str] = None

    createdAt: datetime
    updatedAt: Optional[datetime] = None

    @model_validator(mode="after")
    def _require_media(self) -> "PromoRequest":
        if not self.imagePath and not self.videoPath:
            raise ValueError("Se requiere al menos una foto o un video")
        return self

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
