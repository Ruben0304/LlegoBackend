"""GraphQL queries for business type configurations."""
import strawberry
from typing import List, Optional
from datetime import datetime
from strawberry.types import Info

from .types import BusinessTypeConfigType
from repositories.business_type_repository import business_type_repo
from domain.business_types import BusinessTypeConfig


def convert_to_graphql_type(config: BusinessTypeConfig) -> BusinessTypeConfigType:
    """Convert Pydantic model to GraphQL type."""
    from .types import GradientConfigType, CameraConfigType, FeatureType
    
    return BusinessTypeConfigType(
        id=config.id,
        key=config.key,
        name=config.name,
        description=config.description,
        icon=config.icon,
        model3d_file_name=config.model3dFileName,
        model3d_url=config.model3dUrl,
        model3d_version=config.model3dVersion,
        gradient=GradientConfigType(
            dark_color=config.gradient.darkColor,
            medium_color=config.gradient.mediumColor,
            light_color=config.gradient.lightColor,
            very_light_color=config.gradient.veryLightColor,
            overlay_color=config.gradient.overlayColor
        ),
        camera=CameraConfigType(
            position_x=config.camera.positionX,
            position_y=config.camera.positionY,
            position_z=config.camera.positionZ,
            euler_x=config.camera.eulerX,
            euler_y=config.camera.eulerY,
            euler_z=config.camera.eulerZ
        ),
        glow_color=config.glowColor,
        features=[
            FeatureType(
                icon=f.icon,
                title=f.title,
                subtitle=f.subtitle,
                sort_order=f.sortOrder
            )
            for f in config.features
        ],
        sort_order=config.sortOrder,
        is_active=config.isActive,
        created_at=config.createdAt,
        updated_at=config.updatedAt
    )


@strawberry.type
class BusinessTypeQuery:
    @strawberry.field(description="Get business type configurations (supports incremental sync)")
    async def business_type_configs(
        self,
        info: Info,
        last_sync_at: Optional[datetime] = None
    ) -> List[BusinessTypeConfigType]:
        """
        Get business type configurations.
        
        Args:
            last_sync_at: Optional datetime for incremental sync.
                         If provided, only returns configs modified after this date.
        
        Returns:
            List of active business type configurations sorted by sortOrder.
        """
        if last_sync_at:
            configs = await business_type_repo.get_modified_since(last_sync_at)
        else:
            configs = await business_type_repo.get_all()
        
        return [convert_to_graphql_type(config) for config in configs]
