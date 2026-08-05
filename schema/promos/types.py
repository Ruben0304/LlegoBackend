"""GraphQL type definitions for promo requests."""

from datetime import datetime
from typing import Optional

import strawberry

from domain.promos import PromoRequest
from utils.s3 import get_public_url


@strawberry.type
class PromoRequestType:
    """A promo submitted from the customer app, as seen by the admin app."""

    id: str
    imagePath: Optional[str] = None
    videoPath: Optional[str] = None
    title: Optional[str] = None
    whatsapp: Optional[str] = None
    link: Optional[str] = None
    lugar: Optional[str] = None
    status: str
    rejectionReason: Optional[str] = None
    createdAt: datetime
    reviewedAt: Optional[datetime] = None

    @strawberry.field(description="Public URL for the submitted photo")
    def image_url(self) -> Optional[str]:
        return get_public_url(self.imagePath) if self.imagePath else None

    @strawberry.field(description="Public URL for the submitted video")
    def video_url(self) -> Optional[str]:
        return get_public_url(self.videoPath) if self.videoPath else None


@strawberry.type
class PromoRequestPage:
    """A page of promo requests for the administrative app."""

    items: list[PromoRequestType]
    total: int


def promo_request_to_type(request: PromoRequest) -> PromoRequestType:
    """Map the domain model onto its GraphQL type."""
    return PromoRequestType(
        id=str(request.id),
        imagePath=request.imagePath,
        videoPath=request.videoPath,
        title=request.title,
        whatsapp=request.whatsapp,
        link=request.link,
        lugar=request.lugar,
        status=request.status,
        rejectionReason=request.rejectionReason,
        createdAt=request.createdAt,
        reviewedAt=request.reviewedAt,
    )
