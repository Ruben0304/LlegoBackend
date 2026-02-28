from typing import List, Optional

import strawberry
from strawberry.scalars import JSON

from schema.branches.inputs import (
    CoordinatesInput,
    QrPaymentInput,
    TransferAccountInput,
    TransferPhoneInput,
)
from schema.branches.types import BranchTipo


@strawberry.input
class CreateBusinessInput:
    """Input for creating a new business."""

    name: str
    avatar: Optional[str] = None  # Optional, upload via REST endpoint
    description: Optional[str] = None
    tags: Optional[List[str]] = None


@strawberry.input
class UpdateBusinessInput:
    """Input for updating a business."""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    isActive: Optional[bool] = None
    avatar: Optional[str] = None  # Path from /upload/business/avatar


@strawberry.input
class RegisterBranchInput:
    """Input for creating a branch within register_business mutation."""

    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: JSON
    tipos: List[BranchTipo]  # Obligatorio: ["restaurante", "dulceria", "tienda", "perfumeria"]
    paymentMethodIds: List[str]  # Obligatorio: IDs de métodos de pago aceptados
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Optional, upload via REST endpoint
    coverImage: Optional[str] = None  # Optional, upload via REST endpoint
    socialMedia: Optional[JSON] = None
    # Transfer payment info
    accounts: Optional[List[TransferAccountInput]] = None
    qrPayments: Optional[List[QrPaymentInput]] = None
    phones: Optional[List[TransferPhoneInput]] = None


@strawberry.input
class RegisterBusinessWithBranchesInput:
    """Input for registering a business with its branches in a single operation."""

    business: CreateBusinessInput
    branches: List[RegisterBranchInput]
