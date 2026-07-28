"""Pydantic models for the *promo* feature.

A promo advertises a business that is **not** registered in Llego. Unregistered
businesses reach the team directly (WhatsApp, a call, etc.), and an admin/manager
creates the promo on their behalf from the administrative app — a photo or a
video is required, and a title, WhatsApp number, link and place are optional.

Promos are not shown in the feed until reviewed: they land in
``promo_requests`` with status ``pending`` for an admin/manager to approve or
reject, which is what the moderation fields below track.
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
#   pending   -> created by an admin/manager, awaiting a (possibly different)
#                admin/manager's approval
#   approved  -> reviewed and accepted
#   rejected  -> reviewed and declined (see rejectionReason)
PROMO_REQUEST_STATUSES = ("pending", "approved", "rejected")


# =============================================================================
# Promo request
# =============================================================================


class PromoRequest(BaseModel):
    """A promo for an unregistered business, created by an admin/manager."""

    id: PyObjectId = Field(alias="_id")

    # Media (S3 paths). At least one of the two is required — see the validator.
    imagePath: Optional[str] = None
    videoPath: Optional[str] = None

    # Everything the business may optionally add.
    title: Optional[str] = None
    whatsapp: Optional[str] = None
    link: Optional[str] = None
    lugar: Optional[str] = None

    # The admin/manager that created it.
    createdByUserId: Optional[PyObjectId] = None

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
