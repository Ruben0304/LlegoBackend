"""GraphQL query resolvers for AppConfig entity."""
import strawberry
from typing import Optional

from .types import AppConfigType, BusinessAppConfigType, AndroidConfigType, IosConfigType, MaintenanceConfigType
from models import app_config_repo, business_app_config_repo


@strawberry.type
class AppConfigQueries:
    @strawberry.field(description="Obtener configuración de la aplicación de clientes")
    async def app_config(self) -> Optional[AppConfigType]:
        """Get customer app configuration (versions, maintenance mode, etc.) from Redis cache."""
        config = await app_config_repo.get()
        if not config:
            return None

        return AppConfigType(
            id=config.id,
            android=AndroidConfigType(
                min_version=config.android.minVersion,
                current_version=config.android.currentVersion,
                update_url=config.android.updateUrl,
                store_url=config.android.storeUrl,
                app_size=config.android.appSize
            ),
            ios=IosConfigType(
                min_version=config.ios.minVersion,
                current_version=config.ios.currentVersion,
                store_url=config.ios.storeUrl
            ),
            maintenance=MaintenanceConfigType(
                enabled=config.maintenance.enabled,
                message=config.maintenance.message
            ),
            update_message=config.updateMessage,
            changelog=config.changelog,
            release_date=config.releaseDate
        )

    @strawberry.field(description="Obtener configuración de la aplicación de negocios")
    async def business_app_config(self) -> Optional[BusinessAppConfigType]:
        """Get business/merchant app configuration (versions, maintenance mode, etc.) from Redis cache."""
        config = await business_app_config_repo.get()
        if not config:
            return None

        return BusinessAppConfigType(
            id=config.id,
            android=AndroidConfigType(
                min_version=config.android.minVersion,
                current_version=config.android.currentVersion,
                update_url=config.android.updateUrl,
                store_url=config.android.storeUrl,
                app_size=config.android.appSize
            ),
            ios=IosConfigType(
                min_version=config.ios.minVersion,
                current_version=config.ios.currentVersion,
                store_url=config.ios.storeUrl
            ),
            maintenance=MaintenanceConfigType(
                enabled=config.maintenance.enabled,
                message=config.maintenance.message
            ),
            update_message=config.updateMessage,
            changelog=config.changelog,
            release_date=config.releaseDate
        )
