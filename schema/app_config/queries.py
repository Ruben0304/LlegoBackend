"""GraphQL query resolvers for AppConfig entity."""
import strawberry
from typing import Optional

from .types import (
    AppConfigType,
    BusinessAppConfigType,
    AndroidConfigType,
    CourierAppConfigType,
    IosConfigType,
    MaintenanceConfigType,
    PlatformFeaturesType,
    courier_app_config_to_type,
)
from core.config import settings
from repositories import app_config_repo, business_app_config_repo, courier_app_config_repo
from services.payments.enabled_methods import ENABLED_PAYMENT_METHOD_TYPES
from services.payments.providers.registry import ENABLED_DIGITAL_PROVIDER_CODES


def _digital_method_enabled(method: str) -> bool:
    # Mismo criterio que initiatePayment: el método y su proveedor tienen que estar activos.
    return method in ENABLED_PAYMENT_METHOD_TYPES and method in ENABLED_DIGITAL_PROVIDER_CODES


def platform_features() -> PlatformFeaturesType:
    return PlatformFeaturesType(
        qvapay_enabled=_digital_method_enabled("qvapay"),
        usdt_enabled=_digital_method_enabled("usdt"),
        cash_kyc_enabled=bool(settings.cash_kyc_feature_enabled),
    )


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

    @strawberry.field(
        name="platformFeatures",
        description="Qué funciones de cobro están activas en la plataforma (QvaPay, USDT, KYC de efectivo)",
    )
    def platform_features_field(self) -> PlatformFeaturesType:
        return platform_features()

    @strawberry.field(description="Obtener configuración de la aplicación de choferes (AppMensajeros)")
    async def courier_app_config(self) -> Optional[CourierAppConfigType]:
        """Versiones mínima/actual por plataforma y mantenimiento de la app de
        choferes. Pública, como las otras dos: la app la consulta al arrancar,
        antes de iniciar sesión. Null si aún no se ha configurado."""
        config = await courier_app_config_repo.get()
        if not config:
            return None
        return courier_app_config_to_type(config)
