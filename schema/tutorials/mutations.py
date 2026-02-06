"""GraphQL mutations for Tutorial entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import TutorialType
from .inputs import CreateTutorialInput, UpdateTutorialInput
from models import tutorials_repo
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file


@strawberry.type
class TutorialMutation:
    @strawberry.mutation(description="Create a new tutorial (admin only)")
    async def create_tutorial(
        self,
        info: Info,
        input: CreateTutorialInput,
        jwt: Optional[str] = None
    ) -> TutorialType:
        """
        Create a new tutorial. Upload video first via POST /upload/tutorial/video.
        Only admins can create tutorials.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented
        # For now, any authenticated user can create tutorials
        # In production, add: if user.role != "admin": raise Exception("No autorizado")

        # Create tutorial data
        tutorial_data = {
            "title": input.title,
            "description": input.description,
            "videoUrl": input.videoUrl,
            "duration": input.duration,
            "appTarget": input.appTarget.value,
            "thumbnailUrl": input.thumbnailUrl,
            "order": input.order,
            "isActive": input.isActive,
            "tags": input.tags,
        }

        # Create tutorial in database
        created_tutorial = await tutorials_repo.create(tutorial_data)

        return TutorialType(**created_tutorial.model_dump())

    @strawberry.mutation(description="Update a tutorial (admin only)")
    async def update_tutorial(
        self,
        info: Info,
        id: str,
        input: UpdateTutorialInput,
        jwt: Optional[str] = None
    ) -> TutorialType:
        """
        Update an existing tutorial. Only admins can update tutorials.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented
        # For now, any authenticated user can update tutorials
        # In production, add: if user.role != "admin": raise Exception("No autorizado")

        # Check if tutorial exists
        existing_tutorial = await tutorials_repo.get_by_id(id)
        if not existing_tutorial:
            raise Exception("Tutorial no encontrado")

        # Build updates dict (only include provided fields)
        updates = {}
        if input.title is not None:
            updates["title"] = input.title
        if input.description is not None:
            updates["description"] = input.description
        if input.videoUrl is not None:
            # If video URL changed, optionally delete old video from S3
            # (Uncomment if you want to auto-delete old videos)
            # if existing_tutorial.videoUrl != input.videoUrl:
            #     await delete_file(existing_tutorial.videoUrl)
            updates["videoUrl"] = input.videoUrl
        if input.duration is not None:
            updates["duration"] = input.duration
        if input.appTarget is not None:
            updates["appTarget"] = input.appTarget.value
        if input.thumbnailUrl is not None:
            updates["thumbnailUrl"] = input.thumbnailUrl
        if input.order is not None:
            updates["order"] = input.order
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.tags is not None:
            updates["tags"] = input.tags

        # Update tutorial in database
        updated_tutorial = await tutorials_repo.update(id, updates)
        if not updated_tutorial:
            raise Exception("Error al actualizar tutorial")

        return TutorialType(**updated_tutorial.model_dump())

    @strawberry.mutation(description="Delete a tutorial (admin only)")
    async def delete_tutorial(
        self,
        info: Info,
        id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """
        Delete a tutorial. Only admins can delete tutorials.
        Optionally deletes the video file from S3.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented
        # For now, any authenticated user can delete tutorials
        # In production, add: if user.role != "admin": raise Exception("No autorizado")

        # Get tutorial to delete video from S3
        tutorial = await tutorials_repo.get_by_id(id)
        if not tutorial:
            raise Exception("Tutorial no encontrado")

        # Delete from database
        deleted = await tutorials_repo.delete(id)

        # Optionally delete video from S3
        # (Uncomment if you want to auto-delete videos)
        # if deleted and tutorial.videoUrl:
        #     await delete_file(tutorial.videoUrl)
        # if deleted and tutorial.thumbnailUrl:
        #     await delete_file(tutorial.thumbnailUrl)

        return deleted

    @strawberry.mutation(description="Toggle tutorial active status (admin only)")
    async def toggle_tutorial_active(
        self,
        info: Info,
        id: str,
        jwt: Optional[str] = None
    ) -> TutorialType:
        """
        Toggle the isActive status of a tutorial. Only admins can toggle tutorials.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # TODO: Add admin role check when implemented
        # For now, any authenticated user can toggle tutorials
        # In production, add: if user.role != "admin": raise Exception("No autorizado")

        # Toggle status
        updated_tutorial = await tutorials_repo.toggle_active(id)
        if not updated_tutorial:
            raise Exception("Tutorial no encontrado")

        return TutorialType(**updated_tutorial.model_dump())
