"""GraphQL input types for User mutations."""
import strawberry
from typing import Optional, List


@strawberry.input
class UpdateUserInput:
    """Input for updating user profile."""
    name: Optional[str] = None
    username: Optional[str] = None
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


@strawberry.input
class SavedAddressInput:
    """Input for creating or replacing a saved delivery address."""
    label: str                              # Alias visible (ej: \"Casa\", \"Trabajo\")
    street: str
    latitude: float
    longitude: float
    city: Optional[str] = None
    reference: Optional[str] = None
    addressType: str = "house"              # \"house\" | \"apartment\" | \"office\" | \"other\"
    buildingName: Optional[str] = None
    floor: Optional[str] = None
    apartment: Optional[str] = None
    deliveryInstructions: Optional[str] = None
    setAsDefault: bool = False              # Marcar como dirección por defecto al guardar


@strawberry.input
class UpdateSavedAddressInput:
    """Input for editing an existing saved address (partial update)."""
    addressId: str                          # ID de la dirección a editar
    label: Optional[str] = None
    street: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    reference: Optional[str] = None
    addressType: Optional[str] = None
    buildingName: Optional[str] = None
    floor: Optional[str] = None
    apartment: Optional[str] = None
    deliveryInstructions: Optional[str] = None
    setAsDefault: Optional[bool] = None
