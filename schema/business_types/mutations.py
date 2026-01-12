"""GraphQL mutations for business type configurations and device tokens."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import (
    BusinessTypeConfigType,
    DeviceTokenType,
    CreateBusinessTypeConfigInput,
    UpdateBusinessTypeConfigInput,
    RegisterDeviceTokenInput
)
from repositories.business_type_repository import business_type_repo
from repositories.device_token_repository import device_token_repo
from services.push_notification_service import push_service
from models_business_types import BusinessTypeConfig, DeviceToken
from utils.graphql_auth import apply_jwt, require_admin


def convert_business_type_to_graphql(config: BusinessTypeConfig) -> BusinessTypeConfigType:
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


def convert_device_token_to_graphql(token: DeviceToken) -> DeviceTokenType:
    """Convert Pydantic model to GraphQL type."""
    return DeviceTokenType(
        id=token.id,
        user_id=token.userId,
        token=token.token,
        platform=token.platform,
        app_version=token.appVersion,
        os_version=token.osVersion,
        is_active=token.isActive,
        created_at=token.createdAt,
        updated_at=token.updatedAt
    )


@strawberry.type
class BusinessTypeMutation:
    @strawberry.mutation(description="Register device token for push notifications")
    async def register_device_token(
        self,
        info: Info,
        input: RegisterDeviceTokenInput,
        jwt: Optional[str] = None
    ) -> DeviceTokenType:
        """
        Register a device token for push notifications.
        
        Args:
            input: Device token registration data
            jwt: Optional JWT token (if user is logged in)
        
        Returns:
            Registered device token
        """
        user_id = None
        if jwt:
            try:
                apply_jwt(jwt, info)
                user_id = info.context.get("user_id")
            except:
                # If JWT is invalid, continue without user_id
                pass
        
        token_data = {
            "userId": user_id,
            "token": input.token,
            "platform": input.platform.value,
            "appVersion": input.app_version,
            "osVersion": input.os_version
        }
        
        device_token = await device_token_repo.create_or_update(token_data)
        return convert_device_token_to_graphql(device_token)

    @strawberry.mutation(description="Unregister device token")
    async def unregister_device_token(
        self,
        info: Info,
        token: str
    ) -> bool:
        """
        Unregister a device token (e.g., on logout or app uninstall).
        
        Args:
            token: Device token to unregister
        
        Returns:
            True if successful
        """
        return await device_token_repo.deactivate(token)

    @strawberry.mutation(description="Create new business type configuration (Admin only, triggers push notification)")
    async def create_business_type_config(
        self,
        info: Info,
        input: CreateBusinessTypeConfigInput,
        jwt: str
    ) -> BusinessTypeConfigType:
        """
        Create a new business type configuration.
        This will trigger push notifications to all registered devices.
        
        Args:
            input: Business type configuration data
            jwt: Admin JWT token (required)
        
        Returns:
            Created business type configuration
        
        Raises:
            PermissionError: If user is not an admin
        """
        # Validate admin permission
        apply_jwt(jwt, info)
        require_admin(info)
        
        # Prepare config data
        config_data = {
            "key": input.key,
            "name": input.name,
            "description": input.description,
            "icon": input.icon,
            "model3dFileName": input.model3d_file_name,
            "model3dUrl": input.model3d_url,
            "model3dVersion": 1,
            "gradient": {
                "darkColor": input.gradient.dark_color,
                "mediumColor": input.gradient.medium_color,
                "lightColor": input.gradient.light_color,
                "veryLightColor": input.gradient.very_light_color,
                "overlayColor": input.gradient.overlay_color
            },
            "camera": {
                "positionX": input.camera.position_x,
                "positionY": input.camera.position_y,
                "positionZ": input.camera.position_z,
                "eulerX": input.camera.euler_x,
                "eulerY": input.camera.euler_y,
                "eulerZ": input.camera.euler_z
            },
            "glowColor": input.glow_color,
            "features": [
                {
                    "icon": f.icon,
                    "title": f.title,
                    "subtitle": f.subtitle,
                    "sortOrder": f.sort_order
                }
                for f in input.features
            ],
            "sortOrder": input.sort_order,
            "isActive": True
        }
        
        # Create business type config
        new_config = await business_type_repo.create(config_data)
        
        # Get all active device tokens
        all_tokens = await device_token_repo.get_all_active()
        
        # Group tokens by platform
        ios_tokens = [t.token for t in all_tokens if t.platform == "IOS"]
        android_tokens = [t.token for t in all_tokens if t.platform == "ANDROID"]
        
        # Prepare push notification
        push_title = input.push_title or "¡Nueva categoría disponible!"
        push_body = input.push_body or f"Descubre {input.name} en Llego"
        push_data = {
            "type": "NEW_BUSINESS_TYPE",
            "businessTypeKey": input.key,
            "businessTypeId": new_config.id,
            "action": "SYNC_BUSINESS_TYPES"
        }
        
        # Send push notifications
        if ios_tokens:
            await push_service.send_to_all(ios_tokens, push_title, push_body, push_data, "IOS")
        if android_tokens:
            await push_service.send_to_all(android_tokens, push_title, push_body, push_data, "ANDROID")
        
        return convert_business_type_to_graphql(new_config)

    @strawberry.mutation(description="Update business type configuration (Admin only)")
    async def update_business_type_config(
        self,
        info: Info,
        id: str,
        input: UpdateBusinessTypeConfigInput,
        jwt: str
    ) -> BusinessTypeConfigType:
        """
        Update an existing business type configuration.
        This does NOT trigger push notifications.
        
        Args:
            id: Business type configuration ID
            input: Update data
            jwt: Admin JWT token (required)
        
        Returns:
            Updated business type configuration
        
        Raises:
            PermissionError: If user is not an admin
            ValueError: If configuration not found
        """
        # Validate admin permission
        apply_jwt(jwt, info)
        require_admin(info)
        
        # Prepare update data (only include non-None fields)
        update_data = {}
        
        if input.name is not None:
            update_data["name"] = input.name
        if input.description is not None:
            update_data["description"] = input.description
        if input.icon is not None:
            update_data["icon"] = input.icon
        if input.model3d_file_name is not None:
            update_data["model3dFileName"] = input.model3d_file_name
        if input.model3d_url is not None:
            update_data["model3dUrl"] = input.model3d_url
        if input.model3d_version is not None:
            update_data["model3dVersion"] = input.model3d_version
        if input.gradient is not None:
            update_data["gradient"] = {
                "darkColor": input.gradient.dark_color,
                "mediumColor": input.gradient.medium_color,
                "lightColor": input.gradient.light_color,
                "veryLightColor": input.gradient.very_light_color,
                "overlayColor": input.gradient.overlay_color
            }
        if input.camera is not None:
            update_data["camera"] = {
                "positionX": input.camera.position_x,
                "positionY": input.camera.position_y,
                "positionZ": input.camera.position_z,
                "eulerX": input.camera.euler_x,
                "eulerY": input.camera.euler_y,
                "eulerZ": input.camera.euler_z
            }
        if input.glow_color is not None:
            update_data["glowColor"] = input.glow_color
        if input.features is not None:
            update_data["features"] = [
                {
                    "icon": f.icon,
                    "title": f.title,
                    "subtitle": f.subtitle,
                    "sortOrder": f.sort_order
                }
                for f in input.features
            ]
        if input.sort_order is not None:
            update_data["sortOrder"] = input.sort_order
        if input.is_active is not None:
            update_data["isActive"] = input.is_active
        
        # Update configuration
        updated_config = await business_type_repo.update(id, update_data)
        
        if not updated_config:
            raise ValueError(f"Business type configuration with id {id} not found")
        
        return convert_business_type_to_graphql(updated_config)

    @strawberry.mutation(description="Deactivate business type configuration (Admin only)")
    async def deactivate_business_type_config(
        self,
        info: Info,
        id: str,
        jwt: str
    ) -> BusinessTypeConfigType:
        """
        Deactivate (soft delete) a business type configuration.
        
        Args:
            id: Business type configuration ID
            jwt: Admin JWT token (required)
        
        Returns:
            Deactivated business type configuration
        
        Raises:
            PermissionError: If user is not an admin
            ValueError: If configuration not found
        """
        # Validate admin permission
        apply_jwt(jwt, info)
        require_admin(info)
        
        # Deactivate configuration
        deactivated_config = await business_type_repo.deactivate(id)
        
        if not deactivated_config:
            raise ValueError(f"Business type configuration with id {id} not found")
        
        return convert_business_type_to_graphql(deactivated_config)
