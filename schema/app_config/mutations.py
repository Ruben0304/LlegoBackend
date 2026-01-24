"""GraphQL mutation resolvers for AppConfig entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import AppConfigType, AndroidConfigType, IosConfigType, MaintenanceConfigType
from .inputs import UpdateAppConfigInput
from models import app_config_repo
from utils.graphql_auth import require_role


@strawberry.type
class AppConfigMutations:
    @strawberry.mutation(description="Actualizar configuración de la aplicación (requiere rol admin)")
    async def update_app_config(
        self,
        info: Info,
        input: UpdateAppConfigInput,
        jwt: str
    ) -> Optional[AppConfigType]:
        """
        Update app configuration. Requires admin role.
        Only updates fields that are provided (partial update).
        """
        # Require admin role
        require_role(jwt, info, ["admin"])

        # Get current config
        current_config = await app_config_repo.get()
        if not current_config:
            raise Exception("Configuración de la app no encontrada")

        # Build updates dictionary
        updates = {}

        # Update Android config
        if input.android:
            android_updates = {}
            if input.android.min_version is not None:
                android_updates["minVersion"] = input.android.min_version
            if input.android.current_version is not None:
                android_updates["currentVersion"] = input.android.current_version
            if input.android.update_url is not None:
                android_updates["updateUrl"] = input.android.update_url
            if input.android.store_url is not None:
                android_updates["storeUrl"] = input.android.store_url
            if input.android.app_size is not None:
                android_updates["appSize"] = input.android.app_size

            if android_updates:
                # Merge with current android config
                current_android = current_config.android.model_dump()
                current_android.update(android_updates)
                updates["android"] = current_android

        # Update iOS config
        if input.ios:
            ios_updates = {}
            if input.ios.min_version is not None:
                ios_updates["minVersion"] = input.ios.min_version
            if input.ios.current_version is not None:
                ios_updates["currentVersion"] = input.ios.current_version
            if input.ios.store_url is not None:
                ios_updates["storeUrl"] = input.ios.store_url

            if ios_updates:
                # Merge with current ios config
                current_ios = current_config.ios.model_dump()
                current_ios.update(ios_updates)
                updates["ios"] = current_ios

        # Update maintenance config
        if input.maintenance:
            maintenance_updates = {}
            if input.maintenance.enabled is not None:
                maintenance_updates["enabled"] = input.maintenance.enabled
            if input.maintenance.message is not None:
                maintenance_updates["message"] = input.maintenance.message

            if maintenance_updates:
                # Merge with current maintenance config
                current_maintenance = current_config.maintenance.model_dump()
                current_maintenance.update(maintenance_updates)
                updates["maintenance"] = current_maintenance

        # Update other fields
        if input.update_message is not None:
            updates["updateMessage"] = input.update_message
        if input.changelog is not None:
            updates["changelog"] = input.changelog
        if input.release_date is not None:
            updates["releaseDate"] = input.release_date

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update config in database
        updated_config = await app_config_repo.update(current_config.id, updates)
        if not updated_config:
            raise Exception("Error al actualizar la configuración")

        return AppConfigType(
            id=updated_config.id,
            android=AndroidConfigType(
                min_version=updated_config.android.minVersion,
                current_version=updated_config.android.currentVersion,
                update_url=updated_config.android.updateUrl,
                store_url=updated_config.android.storeUrl,
                app_size=updated_config.android.appSize
            ),
            ios=IosConfigType(
                min_version=updated_config.ios.minVersion,
                current_version=updated_config.ios.currentVersion,
                store_url=updated_config.ios.storeUrl
            ),
            maintenance=MaintenanceConfigType(
                enabled=updated_config.maintenance.enabled,
                message=updated_config.maintenance.message
            ),
            update_message=updated_config.updateMessage,
            changelog=updated_config.changelog,
            release_date=updated_config.releaseDate
        )
