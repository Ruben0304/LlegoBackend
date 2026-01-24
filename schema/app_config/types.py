"""GraphQL type definitions for AppConfig entity."""
import strawberry
from datetime import datetime
from typing import Optional


@strawberry.type
class AndroidConfigType:
    """Android app version configuration."""
    min_version: str = strawberry.field(name="minVersion", description="Minimum version allowed")
    current_version: str = strawberry.field(name="currentVersion", description="Latest available version")
    update_url: str = strawberry.field(name="updateUrl", description="URL to download the update")
    store_url: str = strawberry.field(name="storeUrl", description="Google Play Store URL")
    app_size: str = strawberry.field(name="appSize", description="App size (e.g., '25 MB')")


@strawberry.type
class IosConfigType:
    """iOS app version configuration."""
    min_version: str = strawberry.field(name="minVersion", description="Minimum version allowed")
    current_version: str = strawberry.field(name="currentVersion", description="Latest available version")
    store_url: str = strawberry.field(name="storeUrl", description="App Store URL")


@strawberry.type
class MaintenanceConfigType:
    """Maintenance mode configuration."""
    enabled: bool = strawberry.field(description="Whether maintenance mode is active")
    message: Optional[str] = strawberry.field(description="Message to display during maintenance")


@strawberry.type
class AppConfigType:
    """App version and configuration management for customer app."""
    id: str
    android: AndroidConfigType
    ios: IosConfigType
    maintenance: MaintenanceConfigType
    update_message: Optional[str] = strawberry.field(name="updateMessage", description="Message to show when update is available")
    changelog: Optional[str] = strawberry.field(description="Release notes")
    release_date: datetime = strawberry.field(name="releaseDate", description="Date of the latest release")


@strawberry.type
class BusinessAppConfigType:
    """App version and configuration management for business/merchant app."""
    id: str
    android: AndroidConfigType
    ios: IosConfigType
    maintenance: MaintenanceConfigType
    update_message: Optional[str] = strawberry.field(name="updateMessage", description="Message to show when update is available")
    changelog: Optional[str] = strawberry.field(description="Release notes")
    release_date: datetime = strawberry.field(name="releaseDate", description="Date of the latest release")
