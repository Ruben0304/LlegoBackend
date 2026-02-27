"""Pydantic models for business type configurations and device tokens."""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum
from bson import ObjectId

from .py_object_id import PyObjectId


class DevicePlatform(str, Enum):
    """Device platform enum."""
    IOS = "IOS"
    ANDROID = "ANDROID"


class GradientConfig(BaseModel):
    """Gradient configuration for business type visual."""
    darkColor: str
    mediumColor: str
    lightColor: str
    veryLightColor: str
    overlayColor: str


class CameraConfig(BaseModel):
    """SceneKit camera configuration."""
    positionX: float
    positionY: float
    positionZ: float
    eulerX: Optional[float] = None
    eulerY: Optional[float] = None
    eulerZ: Optional[float] = None


class Feature(BaseModel):
    """Feature/subcategory for business type."""
    icon: str
    title: str
    subtitle: str
    sortOrder: int


class BusinessTypeConfig(BaseModel):
    """Business type configuration model."""
    id: str = Field(alias="_id")
    key: str
    name: str
    description: str
    icon: str
    model3dFileName: str
    model3dUrl: Optional[str] = None
    model3dVersion: int = 1
    gradient: GradientConfig
    camera: CameraConfig
    glowColor: str
    features: List[Feature]
    sortOrder: int
    isActive: bool = True
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class DeviceToken(BaseModel):
    """Device token model for push notifications."""
    id: PyObjectId = Field(alias="_id")
    userId: Optional[PyObjectId] = None
    token: str
    platform: DevicePlatform
    appVersion: Optional[str] = None
    osVersion: Optional[str] = None
    bundleId: Optional[str] = None  # Bundle ID of the app
    environment: str = "sandbox"  # "sandbox" or "production"
    isActive: bool = True
    createdAt: datetime
    updatedAt: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True
