"""GraphQL input types for Branch mutations."""
import strawberry
from typing import Optional, List
from strawberry.scalars import JSON


@strawberry.input
class CoordinatesInput:
    """Input for branch coordinates."""
    lat: float
    lng: float


@strawberry.input
class CreateBranchInput:
    """Input for creating a new branch."""
    businessId: str
    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: JSON
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    deliveryRadius: Optional[float] = None
    facilities: Optional[List[str]] = None


@strawberry.input
class UpdateBranchInput:
    """Input for updating a branch."""
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    schedule: Optional[JSON] = None
    status: Optional[str] = None
    deliveryRadius: Optional[float] = None
    facilities: Optional[List[str]] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
