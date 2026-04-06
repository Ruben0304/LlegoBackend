"""GraphQL input types for Branch mutations."""

from typing import List, Optional

import strawberry
from strawberry.scalars import JSON

from .types import AcceptedCurrency, BranchTipo, BranchVehicle


@strawberry.input
class CoordinatesInput:
    """Input for branch coordinates."""

    lat: float
    lng: float


@strawberry.input
class TransferAccountInput:
    """Input for a bank card account for CUP transfers."""

    cardNumber: str
    confirmPhone: str
    cardHolderName: Optional[str] = None
    isActive: bool = True


@strawberry.input
class CreateBranchInput:
    """Input for creating a new branch."""

    businessId: str
    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: JSON
    tipos: List[
        BranchTipo
    ]  # Obligatorio: ["restaurante", "dulceria", "tienda", "perfumeria"]
    paymentMethodIds: List[str]  # Obligatorio: IDs de mÃ©todos de pago aceptados
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    socialMedia: Optional[JSON] = None
    useAppMessaging: bool = (
        True  # True = mensajerÃ­a por la app, False = por cuenta propia
    )
    pickupEnabled: bool = False
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )
    acceptedCurrency: Optional[AcceptedCurrency] = None  # "CUP", "USD", or "BOTH"
    exchangeRate: Optional[int] = (
        None  # Tasa de cambio (solo si acceptedCurrency es "BOTH")
    )
    # Transfer payment info (single source of truth)
    accounts: Optional[List[TransferAccountInput]] = None
    cashKycEnabled: bool = False
    cashKycPolicyVersion: str = "cash-kyc-v1"
    cashKycMinConfidence: float = 0.85
    cashKycTtlDays: int = 30


@strawberry.input
class UpdateBranchInput:
    """Input for updating a branch."""

    name: Optional[str] = None
    address: Optional[str] = None
    coordinates: Optional[CoordinatesInput] = None  # For updating location
    phone: Optional[str] = None
    schedule: Optional[JSON] = None
    isActive: Optional[bool] = None
    socialMedia: Optional[JSON] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    tipos: Optional[List[BranchTipo]] = (
        None  # ["restaurante", "dulceria", "tienda", "perfumeria"]
    )
    paymentMethodIds: Optional[List[str]] = None  # IDs de mÃ©todos de pago aceptados
    useAppMessaging: Optional[bool] = (
        None  # True = mensajerÃ­a por la app, False = por cuenta propia
    )
    pickupEnabled: Optional[bool] = None
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )
    acceptedCurrency: Optional[AcceptedCurrency] = None  # "CUP", "USD", or "BOTH"
    exchangeRate: Optional[int] = (
        None  # Tasa de cambio (solo si acceptedCurrency es "BOTH")
    )
    # Transfer payment info (single source of truth)
    accounts: Optional[List[TransferAccountInput]] = None
    # QvaPay / Zelle (TronDealer) acceptance
    acceptsQvapay: Optional[bool] = None
    acceptsZelle: Optional[bool] = None  # True habilita TronDealer/USDT
    qvapayUsername: Optional[str] = None  # Username QvaPay para reenvÃ­os manuales
    zelleEmail: Optional[str] = None  # Email Zelle asociado a TronDealer
    cashKycEnabled: Optional[bool] = None
    cashKycPolicyVersion: Optional[str] = None
    cashKycMinConfidence: Optional[float] = None
    cashKycTtlDays: Optional[int] = None
    forceReverify: Optional[bool] = None
