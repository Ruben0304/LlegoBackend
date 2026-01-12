"""GraphQL queries for business type configurations."""
import strawberry
from typing import List, Optional
from datetime import datetime
from strawberry.types import Info

from .types import BusinessTypeConfigType
from repositories.business_type_repository import business_type_repo
from models_business_types import BusinessTypeConfig


def convert_to_graphql_type(config: BusinessTypeConfig) -> BusinessTypeConfigType:
    """Convert Pydantic model to GraphQL type."""
    return BusinessTypeConfigType(
        id=config.id,
        key=config.key,
        name=config.name,
        description=config.description,
        icon=config.icon,
        model3d_file_name=config.model3dFileName,
        model3d_url=config.model3dUrl,
        model3d_version=config.model3dVersion,
        gradient=config.gradient,
        camera=config.camera,
        glow_color=config.glowColor,
        features=config.features,
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
