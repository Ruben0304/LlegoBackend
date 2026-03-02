"""GraphQL mutations for Showcase entity."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import showcases_repo
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file

from .inputs import CreateShowcaseInput, UpdateShowcaseInput
from .types import ShowcaseType, showcase_to_type


@strawberry.type
class ShowcaseMutation:
    @strawberry.mutation(description="Crear una vitrina")
    async def create_showcase(
        self, info: Info, input: CreateShowcaseInput, jwt: Optional[str] = None
    ) -> ShowcaseType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        await access_checker.require_branch_access(user_id, input.branchId)

        showcase_data = {
            "branchId": input.branchId,
            "title": input.title,
            "image": input.image,
            "description": input.description,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "availability": item.availability,
                }
                for item in input.items
            ]
            if input.items is not None
            else None,
            "isActive": True,
        }

        showcase = await showcases_repo.create(showcase_data)
        return showcase_to_type(showcase)

    @strawberry.mutation(description="Actualizar una vitrina")
    async def update_showcase(
        self,
        info: Info,
        showcase_id: str,
        input: UpdateShowcaseInput,
        jwt: Optional[str] = None,
    ) -> ShowcaseType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        showcase = await showcases_repo.get_by_id(showcase_id)
        if not showcase:
            raise Exception("Vitrina no encontrada")

        await access_checker.require_branch_access(user_id, showcase.branchId)

        updates = {}
        if input.title is not None:
            updates["title"] = input.title
        if input.description is not None:
            updates["description"] = input.description
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.items is not None:
            updates["items"] = [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "availability": item.availability,
                }
                for item in input.items
            ]
        if input.image is not None:
            if showcase.image:
                await delete_file(showcase.image)
            updates["image"] = input.image

        if not updates:
            raise Exception("No hay campos para actualizar")

        updated = await showcases_repo.update(showcase_id, updates)
        if not updated:
            raise Exception("Error al actualizar la vitrina")

        return showcase_to_type(updated)

    @strawberry.mutation(description="Eliminar una vitrina")
    async def delete_showcase(
        self, info: Info, showcase_id: str, jwt: Optional[str] = None
    ) -> bool:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        showcase = await showcases_repo.get_by_id(showcase_id)
        if not showcase:
            raise Exception("Vitrina no encontrada")

        await access_checker.require_branch_access(user_id, showcase.branchId)

        if showcase.image:
            await delete_file(showcase.image)

        return await showcases_repo.delete(showcase_id)

    @strawberry.mutation(description="Cambiar disponibilidad de una vitrina")
    async def toggle_showcase_availability(
        self,
        info: Info,
        showcase_id: str,
        is_active: bool,
        jwt: Optional[str] = None,
    ) -> ShowcaseType:
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        showcase = await showcases_repo.get_by_id(showcase_id)
        if not showcase:
            raise Exception("Vitrina no encontrada")

        await access_checker.require_branch_access(user_id, showcase.branchId)
        await showcases_repo.update_availability(showcase_id, is_active)

        updated = await showcases_repo.get_by_id(showcase_id)
        if not updated:
            raise Exception("Error al actualizar la disponibilidad de la vitrina")

        return showcase_to_type(updated)
