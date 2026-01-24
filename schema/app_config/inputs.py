"""GraphQL input types for AppConfig mutations."""
import strawberry
from typing import Optional
from datetime import datetime


@strawberry.input
class UpdateAndroidConfigInput:
    """Input for updating Android configuration."""
    min_version: Optional[str] = strawberry.field(name="minVersion", default=None)
    current_version: Optional[str] = strawberry.field(name="currentVersion", default=None)
    update_url: Optional[str] = strawberry.field(name="updateUrl", default=None)
    store_url: Optional[str] = strawberry.field(name="storeUrl", default=None)
    app_size: Optional[str] = strawberry.field(name="appSize", default=None)


@strawberry.input
class UpdateIosConfigInput:
    """Input for updating iOS configuration."""
    min_version: Optional[str] = strawberry.field(name="minVersion", default=None)
    current_version: Optional[str] = strawberry.field(name="currentVersion", default=None)
    store_url: Optional[str] = strawberry.field(name="storeUrl", default=None)


@strawberry.input
class UpdateMaintenanceConfigInput:
    """Input for updating maintenance mode configuration."""
    enabled: Optional[bool] = None
    message: Optional[str] = None


@strawberry.input
class UpdateAppConfigInput:
    """Input for updating app configuration."""
    android: Optional[UpdateAndroidConfigInput] = None
    ios: Optional[UpdateIosConfigInput] = None
    maintenance: Optional[UpdateMaintenanceConfigInput] = None
    update_message: Optional[str] = strawberry.field(name="updateMessage", default=None)
    changelog: Optional[str] = None
    release_date: Optional[datetime] = strawberry.field(name="releaseDate", default=None)
