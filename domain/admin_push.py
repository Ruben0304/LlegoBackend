"""Notificaciones push enviadas a mano desde el Panel Admin."""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class AdminPushTarget(str, Enum):
    USERS = "users"  # todos los dispositivos de unas cuentas
    DEVICES = "devices"  # dispositivos concretos (incluye los sin sesión)
    APP = "app"  # todos los dispositivos de una app


class AdminPushNotification(BaseModel):
    id: PyObjectId = Field(alias="_id")
    title: str
    body: str
    target: AdminPushTarget
    audience: Optional[str] = None  # "customer" | "business"
    platform: Optional[str] = None  # "IOS" | "ANDROID"
    userIds: List[str] = []
    deviceIds: List[str] = []
    totalDevices: int = 0
    sent: int = 0
    failed: int = 0
    simulated: bool = False
    sentById: str
    sentByName: Optional[str] = None
    createdAt: datetime

    class Config:
        populate_by_name = True
        use_enum_values = True
