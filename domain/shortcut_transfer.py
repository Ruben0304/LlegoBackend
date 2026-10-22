"""Shortcut transfer model for bank transfers registered via iOS Shortcuts."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class ShortcutTransfer(BaseModel):
    """
    Represents a bank transfer registered from an iOS Shortcut.

    When a bank SMS is received, the shortcut extracts the transfer data
    and sends it to the API. The app later queries for pending transfers
    to automatically confirm payments.
    """

    id: PyObjectId = Field(alias="_id")
    transfer_id: str  # Bank transfer ID extracted from SMS
    amount: float  # Transfer amount
    phone: Optional[str] = None  # Phone number that received the SMS
    # `phone` normalizado a los 8 dígitos nacionales (utils.phone) para comparar sin
    # depender del formato; None si no es un número cubano o en registros antiguos.
    phone_national: Optional[str] = None
    date: Optional[datetime] = None  # Transfer date from SMS
    # Método de pago (cuenta receptora) al que llegó la transferencia. Si viene, solo puede
    # confirmar pagos hechos con ese método; sin él (Atajos antiguos) vale para cualquiera.
    payment_method_id: Optional[str] = None
    activated: bool = False  # Whether this transfer has been used to confirm a payment
    activated_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
