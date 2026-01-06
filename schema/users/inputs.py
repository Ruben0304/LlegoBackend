"""GraphQL input types for User mutations."""
import strawberry
from typing import Optional, List


@strawberry.input
class UpdateUserInput:
    """Input for updating user profile."""
    name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None  # Path from /upload/user/avatar endpoint


@strawberry.input
class AddBranchToUserInput:
    """Input for adding a branch to a user."""
    branchId: str


@strawberry.input
class UpdateLocationInput:
    """Input for updating user location."""
    longitude: float  # X coordinate
    latitude: float   # Y coordinate
