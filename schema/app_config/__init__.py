"""GraphQL schema for app configuration."""
from .types import AndroidConfigType, IosConfigType, MaintenanceConfigType, AppConfigType, BusinessAppConfigType
from .queries import AppConfigQueries
from .mutations import AppConfigMutations
from .inputs import UpdateAndroidConfigInput, UpdateIosConfigInput, UpdateMaintenanceConfigInput, UpdateAppConfigInput

__all__ = [
    "AndroidConfigType",
    "IosConfigType",
    "MaintenanceConfigType",
    "AppConfigType",
    "BusinessAppConfigType",
    "AppConfigQueries",
    "AppConfigMutations",
    "UpdateAndroidConfigInput",
    "UpdateIosConfigInput",
    "UpdateMaintenanceConfigInput",
    "UpdateAppConfigInput",
]
