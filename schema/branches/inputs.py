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
    cardHolderName: str
    bankName: str
    isActive: bool = True


@strawberry.input
class QrPaymentInput:
    """Input for a QR payment value (EnZona, etc.)."""

    value: str
    isActive: bool = True


@strawberry.input
class TransferPhoneInput:
    """Input for a phone number for mobile transfers (Transfermóvil, etc.)."""

    phone: str
    isActive: bool = True


@strawberry.input
class CreateBranchInput:
    """Input for creating a new branch."""

    businessId: str
    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: JSON
    tipos: List[BranchTipo]  # Obligatorio: ["restaurante", "dulceria", "tienda", "perfumeria"]
    paymentMethodIds: List[str]  # Obligatorio: IDs de métodos de pago aceptados
    address: Optional[str] = None
    managerIds: Optional[List[str]] = None
    avatar: Optional[str] = None  # Path from /upload/branch/avatar
    coverImage: Optional[str] = None  # Path from /upload/branch/cover
    socialMedia: Optional[JSON] = None
    useAppMessaging: bool = (
        True  # True = mensajería por la app, False = por cuenta propia
    )
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )
    acceptedCurrency: Optional[AcceptedCurrency] = None  # "CUP", "USD", or "BOTH"
    exchangeRate: Optional[int] = None  # Tasa de cambio (solo si acceptedCurrency es "BOTH")
    # Transfer payment info
    accounts: Optional[List[TransferAccountInput]] = None
    qrPayments: Optional[List[QrPaymentInput]] = None
    phones: Optional[List[TransferPhoneInput]] = None


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
    tipos: Optional[List[BranchTipo]] = None  # ["restaurante", "dulceria", "tienda", "perfumeria"]
    paymentMethodIds: Optional[List[str]] = None  # IDs de métodos de pago aceptados
    useAppMessaging: Optional[bool] = (
        None  # True = mensajería por la app, False = por cuenta propia
    )
    vehicles: Optional[List[BranchVehicle]] = (
        None  # ["moto", "bicicleta", "carro", "camioneta", "caminando"]
    )
    acceptedCurrency: Optional[AcceptedCurrency] = None  # "CUP", "USD", or "BOTH"
    exchangeRate: Optional[int] = None  # Tasa de cambio (solo si acceptedCurrency es "BOTH")
    # Transfer payment info
    accounts: Optional[List[TransferAccountInput]] = None
    qrPayments: Optional[List[QrPaymentInput]] = None
    phones: Optional[List[TransferPhoneInput]] = None
    # QvaPay / Zelle (TronDealer) acceptance
    acceptsQvapay: Optional[bool] = None
    acceptsZelle: Optional[bool] = None         # True habilita TronDealer/USDT
    qvapayUsername: Optional[str] = None        # Username QvaPay para reenvíos manuales
    zelleEmail: Optional[str] = None            # Email Zelle asociado a TronDealer
