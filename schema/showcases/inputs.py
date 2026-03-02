"""GraphQL input types for Showcase mutations."""

from typing import Optional

import strawberry


@strawberry.input
class ShowcaseItemInput:
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    availability: bool = True


@strawberry.input
class CreateShowcaseInput:
    branchId: str
    title: str
    image: str  # Path from upload endpoint
    description: Optional[str] = None
    items: Optional[list[ShowcaseItemInput]] = None


@strawberry.input
class UpdateShowcaseInput:
    title: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None
    items: Optional[list[ShowcaseItemInput]] = None
    isActive: Optional[bool] = None
