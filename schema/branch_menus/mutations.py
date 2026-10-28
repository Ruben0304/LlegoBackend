"""GraphQL mutations for branch menu OCR."""

import logging
from typing import Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from repositories import branch_menus_repo
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file

from .types import BranchMenuType, menu_to_type

logger = logging.getLogger(__name__)

# S3 folder written by the menu upload endpoint (api/endpoints/uploads.py)
MENU_IMAGE_PREFIX = "branch_menus/"


def _owns_image(branch_id: str, image: str) -> bool:
    return (
        ObjectId.is_valid(branch_id)
        and image.startswith(f"{MENU_IMAGE_PREFIX}{ObjectId(branch_id)}/")
        and ".." not in image
    )


@strawberry.type
class BranchMenuMutation:
    @strawberry.mutation(description="Upload or update branch menu image")
    async def set_branch_menu(
        self, info: Info, branch_id: str, image: str, jwt: Optional[str] = None
    ) -> BranchMenuType:
        """
        Create or update the menu image for a branch.

        Args:
            branch_id: Branch ID
            image: S3 path to the image (relative path)
            jwt: JWT token

        Returns:
            Updated BranchMenu

        Raises:
            Exception: If user not authenticated, no branch access, or image is empty
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch access
        await access_checker.require_branch_access(user_id, branch_id)

        # The key must come from POST /upload/branch-menu/image. Without this check a
        # branch manager could point at any S3 object and, when the menu is later
        # replaced or deleted, make the server delete it.
        image = (image or "").strip()
        if not image:
            raise Exception("La imagen no puede estar vacía")
        if not _owns_image(branch_id, image):
            raise Exception("Imagen de carta inválida: súbela con /upload/branch-menu/image")

        # Upsert menu
        menu, previous_image = await branch_menus_repo.upsert_image(branch_id, image)

        # Clean up previous image if it existed and is different
        if previous_image and previous_image != image and _owns_image(branch_id, previous_image):
            try:
                await delete_file(previous_image)
            except Exception as e:
                logger.error(f"Failed to delete previous menu image {previous_image}: {e}")

        return menu_to_type(menu)

    @strawberry.mutation(description="Delete branch menu")
    async def delete_branch_menu(
        self, info: Info, branch_id: str, jwt: Optional[str] = None
    ) -> bool:
        """
        Delete menu for a branch.

        Args:
            branch_id: Branch ID
            jwt: JWT token

        Returns:
            True if menu existed and was deleted, False otherwise
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch access
        await access_checker.require_branch_access(user_id, branch_id)

        # Delete menu
        deleted = await branch_menus_repo.delete_by_branch(branch_id)

        # Clean up image from S3 if document existed
        if deleted and deleted.image and _owns_image(branch_id, deleted.image):
            try:
                await delete_file(deleted.image)
            except Exception as e:
                logger.error(f"Failed to delete menu image {deleted.image}: {e}")

        return deleted is not None

    @strawberry.mutation(description="Toggle menu active/inactive status")
    async def toggle_branch_menu(
        self, info: Info, branch_id: str, is_active: bool, jwt: Optional[str] = None
    ) -> BranchMenuType:
        """
        Toggle menu active/inactive status.

        Args:
            branch_id: Branch ID
            is_active: New active status
            jwt: JWT token

        Returns:
            Updated BranchMenu

        Raises:
            Exception: If user not authenticated, no branch access, or menu not found
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch access
        await access_checker.require_branch_access(user_id, branch_id)

        # Update menu
        menu = await branch_menus_repo.set_active(branch_id, is_active)
        if not menu:
            raise Exception("Carta no encontrada")

        return menu_to_type(menu)
