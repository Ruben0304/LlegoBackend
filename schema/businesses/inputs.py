import strawberry
from typing import Optional, List
from strawberry.scalars import JSON
from schema.branches.inputs import CoordinatesInput
from schema.branches.types import BranchTipo


@strawberry.input
class CreateBusinessInput:
    """Input for creating a new business."""
    name: str
    avatar: Optional[str] = None  # Optional, upload via REST endpoint
    coverImage: Optional[str] = None
    description: Optional[str] = None
    socialMedia: Optional[JSON] = None
    tags: Optional[List[str]] = None


@strawberry.input
class UpdateBusinessInput:
    """Input for updating a business."""
    name: Optional[str] = None
    description: Optional[str] = None
    socialMedia: Optional[JSON] = None
    tags: Optional[List[str]] = None
    isActive: Optional[bool] = None
    avatar: Optional[str] = None  # Path from /upload/business/avatar
    coverImage: Optional[str] = None  # Path from /upload/business/cover


@strawberry.input
class RegisterBranchInput:
    """Input for creating a branch within register_business mutation."""
    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: JSON
    tipos: List[BranchTipo]  # Obligatorio: ["restaurante", "dulceria", "tienda"]
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Optional, upload via REST endpoint
    coverImage: Optional[str] = None  # Optional, upload via REST endpoint
    deliveryRadius: Optional[float] = None
    facilities: Optional[List[str]] = None
