"""GraphQL types for business type configurations and device tokens."""
import strawberry
from typing import List, Optional
from datetime import datetime
from enum import Enum


@strawberry.enum
class DevicePlatformEnum(Enum):
    """Device platform enum."""
    IOS = "IOS"
    ANDROID = "ANDROID"


@strawberry.type
class GradientConfigType:
    """Gradient configuration for business type visual."""
    dark_color: str = strawberry.field(name="darkColor")
    medium_color: str = strawberry.field(name="mediumColor")
    light_color: str = strawberry.field(name="lightColor")
    very_light_color: str = strawberry.field(name="veryLightColor")
    overlay_color: str = strawberry.field(name="overlayColor")


@strawberry.type
class CameraConfigType:
    """SceneKit camera configuration."""
    position_x: float = strawberry.field(name="positionX")
    position_y: float = strawberry.field(name="positionY")
    position_z: float = strawberry.field(name="positionZ")
    euler_x: Optional[float] = strawberry.field(name="eulerX", default=None)
    euler_y: Optional[float] = strawberry.field(name="eulerY", default=None)
    euler_z: Optional[float] = strawberry.field(name="eulerZ", default=None)


@strawberry.type
class FeatureType:
    """Feature/subcategory for business type."""
    icon: str
    title: str
    subtitle: str
    sort_order: int = strawberry.field(name="sortOrder")


@strawberry.type
class BusinessTypeConfigType:
    """Business type configuration."""
    id: str
    key: str
    name: str
    description: str
    icon: str
    model3d_file_name: str = strawberry.field(name="model3dFileName")
    model3d_url: Optional[str] = strawberry.field(name="model3dUrl", default=None)
    model3d_version: int = strawberry.field(name="model3dVersion")
    gradient: GradientConfigType
    camera: CameraConfigType
    glow_color: str = strawberry.field(name="glowColor")
    features: List[FeatureType]
    sort_order: int = strawberry.field(name="sortOrder")
    is_active: bool = strawberry.field(name="isActive")
    created_at: datetime = strawberry.field(name="createdAt")
    updated_at: datetime = strawberry.field(name="updatedAt")


@strawberry.type
class DeviceTokenType:
    """Device token for push notifications."""
    id: str
    user_id: Optional[str] = strawberry.field(name="userId", default=None)
    token: str
    platform: DevicePlatformEnum
    app_version: Optional[str] = strawberry.field(name="appVersion", default=None)
    os_version: Optional[str] = strawberry.field(name="osVersion", default=None)
    is_active: bool = strawberry.field(name="isActive")
    created_at: datetime = strawberry.field(name="createdAt")
    updated_at: datetime = strawberry.field(name="updatedAt")


# Input types
@strawberry.input
class GradientConfigInput:
    """Gradient configuration input."""
    dark_color: str = strawberry.field(name="darkColor")
    medium_color: str = strawberry.field(name="mediumColor")
    light_color: str = strawberry.field(name="lightColor")
    very_light_color: str = strawberry.field(name="veryLightColor")
    overlay_color: str = strawberry.field(name="overlayColor")


@strawberry.input
class CameraConfigInput:
    """Camera configuration input."""
    position_x: float = strawberry.field(name="positionX")
    position_y: float = strawberry.field(name="positionY")
    position_z: float = strawberry.field(name="positionZ")
    euler_x: Optional[float] = strawberry.field(name="eulerX", default=None)
    euler_y: Optional[float] = strawberry.field(name="eulerY", default=None)
    euler_z: Optional[float] = strawberry.field(name="eulerZ", default=None)


@strawberry.input
class FeatureInput:
    """Feature input."""
    icon: str
    title: str
    subtitle: str
    sort_order: int = strawberry.field(name="sortOrder")


@strawberry.input
class CreateBusinessTypeConfigInput:
    """Input for creating a business type configuration."""
    key: str
    name: str
    description: str
    icon: str
    model3d_file_name: str = strawberry.field(name="model3dFileName")
    model3d_url: Optional[str] = strawberry.field(name="model3dUrl", default=None)
    gradient: GradientConfigInput
    camera: CameraConfigInput
    glow_color: str = strawberry.field(name="glowColor")
    features: List[FeatureInput]
    sort_order: int = strawberry.field(name="sortOrder")
    push_title: Optional[str] = strawberry.field(name="pushTitle", default=None)
    push_body: Optional[str] = strawberry.field(name="pushBody", default=None)


@strawberry.input
class UpdateBusinessTypeConfigInput:
    """Input for updating a business type configuration."""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    model3d_file_name: Optional[str] = strawberry.field(name="model3dFileName", default=None)
    model3d_url: Optional[str] = strawberry.field(name="model3dUrl", default=None)
    model3d_version: Optional[int] = strawberry.field(name="model3dVersion", default=None)
    gradient: Optional[GradientConfigInput] = None
    camera: Optional[CameraConfigInput] = None
    glow_color: Optional[str] = strawberry.field(name="glowColor", default=None)
    features: Optional[List[FeatureInput]] = None
    sort_order: Optional[int] = strawberry.field(name="sortOrder", default=None)
    is_active: Optional[bool] = strawberry.field(name="isActive", default=None)


@strawberry.input
class RegisterDeviceTokenInput:
    """Input for registering a device token."""
    token: str
    platform: DevicePlatformEnum
    app_version: Optional[str] = strawberry.field(name="appVersion", default=None)
    os_version: Optional[str] = strawberry.field(name="osVersion", default=None)
