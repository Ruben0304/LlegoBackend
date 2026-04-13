"""GraphQL input types for Branch mutations."""

from typing import List, Optional

import strawberry
from strawberry.scalars import JSON

from domain.models import BranchSchedule, DaySchedule, TemporaryStatus, TimeRange

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
class TimeRangeInput:
    """A single open/close time range in HH:MM 24h format."""

    open: str
    close: str


@strawberry.input
class DayRangeInput:
    """
    Schedule input for a range of days sharing the same hours.
    fromDay and toDay use 0=Dom, 1=Lun, ..., 6=Sab.
    """

    fromDay: int
    toDay: int
    isOpen: bool = True
    hours: List[TimeRangeInput] = strawberry.field(default_factory=list)


@strawberry.input
class TemporaryStatusInput:
    """Temporary override for branch open/closed status."""

    temporallyClosed: bool = False
    temporallyOpen: bool = False
    reason: Optional[str] = None


@strawberry.input
class BranchScheduleInput:
    """
    Weekly schedule input. Accepts day ranges that are expanded to 7 individual
    day entries on save. Days not covered by any range default to closed.
    """

    ranges: List[DayRangeInput]
    temporaryStatus: Optional[TemporaryStatusInput] = None


def expand_schedule_input(schedule_input: BranchScheduleInput) -> BranchSchedule:
    """Expand a BranchScheduleInput (with day ranges) into a full BranchSchedule."""
    days_map: dict[int, DaySchedule] = {}

    for range_item in schedule_input.ranges:
        from_day = range_item.fromDay
        to_day = range_item.toDay
        day_indices = (
            list(range(from_day, to_day + 1))
            if from_day <= to_day
            else list(range(from_day, 7)) + list(range(0, to_day + 1))
        )
        hours = [TimeRange(open=h.open, close=h.close) for h in range_item.hours]
        for day in day_indices:
            days_map[day] = DaySchedule(day=day, isOpen=range_item.isOpen, hours=hours)

    days = [
        days_map.get(d, DaySchedule(day=d, isOpen=False, hours=[]))
        for d in range(7)
    ]

    temporary_status = None
    if schedule_input.temporaryStatus:
        ts = schedule_input.temporaryStatus
        temporary_status = TemporaryStatus(
            temporallyClosed=ts.temporallyClosed,
            temporallyOpen=ts.temporallyOpen,
            reason=ts.reason,
        )

    return BranchSchedule(days=days, temporaryStatus=temporary_status)


@strawberry.input
class CreateBranchInput:
    """Input for creating a new branch."""

    businessId: str
    name: str
    coordinates: CoordinatesInput
    phone: str
    schedule: BranchScheduleInput
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
    schedule: Optional[BranchScheduleInput] = None
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
    catalogOnly: Optional[bool] = None  # True = solo catálogo, sin pedidos ni mensajería
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
