"""GraphQL mutations for PromotionalVideo entity."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import promotional_videos_repo
from utils.graphql_auth import apply_optional_jwt
from utils.serialization import to_strawberry_dict

from .inputs import CreatePromotionalVideoInput, UpdatePromotionalVideoInput
from .types import PromotionalVideoType


@strawberry.type
class PromotionalVideoMutation:
    @strawberry.mutation(description="Create a new promotional video (admin only)")
    async def create_promotional_video(
        self, info: Info, input: CreatePromotionalVideoInput, jwt: Optional[str] = None
    ) -> PromotionalVideoType:
        """
        Create a new promotional video. Upload video first via
        POST /upload/promotion/video. Only admins should create promos.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented

        video_data = {
            "title": input.title,
            "description": input.description,
            "videoUrl": input.videoUrl,
            "duration": input.duration,
            "appTarget": input.appTarget.value,
            "thumbnailUrl": input.thumbnailUrl,
            "branchId": input.branchId,
            "order": input.order,
            "isActive": input.isActive,
            "tags": input.tags,
        }

        created = await promotional_videos_repo.create(video_data)
        return PromotionalVideoType(**to_strawberry_dict(created))

    @strawberry.mutation(description="Update a promotional video (admin only)")
    async def update_promotional_video(
        self,
        info: Info,
        id: str,
        input: UpdatePromotionalVideoInput,
        jwt: Optional[str] = None,
    ) -> PromotionalVideoType:
        """Update an existing promotional video. Only admins should update promos."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented

        existing = await promotional_videos_repo.get_by_id(id)
        if not existing:
            raise Exception("Video promocional no encontrado")

        updates = {}
        if input.title is not None:
            updates["title"] = input.title
        if input.description is not None:
            updates["description"] = input.description
        if input.videoUrl is not None:
            updates["videoUrl"] = input.videoUrl
        if input.duration is not None:
            updates["duration"] = input.duration
        if input.appTarget is not None:
            updates["appTarget"] = input.appTarget.value
        if input.thumbnailUrl is not None:
            updates["thumbnailUrl"] = input.thumbnailUrl
        if input.branchId is not None:
            updates["branchId"] = input.branchId
        if input.order is not None:
            updates["order"] = input.order
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.tags is not None:
            updates["tags"] = input.tags

        updated = await promotional_videos_repo.update(id, updates)
        if not updated:
            raise Exception("Error al actualizar video promocional")

        return PromotionalVideoType(**to_strawberry_dict(updated))

    @strawberry.mutation(description="Delete a promotional video (admin only)")
    async def delete_promotional_video(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> bool:
        """Delete a promotional video. Only admins should delete promos."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented

        video = await promotional_videos_repo.get_by_id(id)
        if not video:
            raise Exception("Video promocional no encontrado")

        return await promotional_videos_repo.delete(id)

    @strawberry.mutation(
        description="Toggle promotional video active status (admin only)"
    )
    async def toggle_promotional_video_active(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> PromotionalVideoType:
        """Toggle the isActive status of a promotional video."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented

        updated = await promotional_videos_repo.toggle_active(id)
        if not updated:
            raise Exception("Video promocional no encontrado")

        return PromotionalVideoType(**to_strawberry_dict(updated))
