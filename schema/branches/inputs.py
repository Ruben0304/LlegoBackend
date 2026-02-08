"""GraphQL input types for Branch mutations."""

from typing import List, Optional

import strawberry
from strawberry.scalars import JSON

from .types import BranchTipo, BranchVehicle


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
    tipos: List[BranchTipo]  # Obligatorio: ["restaurante", "dulceria", "tienda"]
    paymentMethodIds: List[str]  # Obligatorio: IDs de métodos de pago aceptados
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    deliveryRadius: Optional[float] = None
    facilities: Optional[List[str]] = None
    useAppMessaging: bool = (
        True  # True = mensajería por la app, False = por cuenta propia
    )
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )


@strawberry.input
class UpdateBranchInput:
    """Input for updating a branch."""

    name: Optional[str] = None
    address: Optional[str] = None
    coordinates: Optional[CoordinatesInput] = None  # For updating location
    phone: Optional[str] = None
    schedule: Optional[JSON] = None
    status: Optional[str] = None
    deliveryRadius: Optional[float] = None
    facilities: Optional[List[str]] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    tipos: Optional[List[BranchTipo]] = None  # ["restaurante", "dulceria", "tienda"]
    paymentMethodIds: Optional[List[str]] = None  # IDs de métodos de pago aceptados
    useAppMessaging: Optional[bool] = (
        None  # True = mensajería por la app, False = por cuenta propia
    )
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )
