"""GraphQL mutations for Showcase entity."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import showcases_repo
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import clave_en_carpeta, delete_file

from .inputs import CreateShowcaseInput, UpdateShowcaseInput
from .types import ShowcaseType, showcase_to_type


def _items(items):
    """Ítems de la vitrina; un precio negativo daba totales negativos en el pedido."""
    if items is None:
        return None
    for item in items:
        if item.price is not None and item.price < 0:
            raise Exception("El precio no puede ser negativo")
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "price": item.price,
            "availability": item.availability,
        }
        for item in items
    ]


def _imagen(image):
    # Solo imágenes subidas a su carpeta: la ruta la manda el cliente
    if image and not clave_en_carpeta(image, "showcases"):
        raise Exception("La imagen de la vitrina no es válida: súbela de nuevo")
    return image


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
            "image": _imagen(input.image),
            "description": input.description,
            "items": _items(input.items),
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
            updates["items"] = _items(input.items)
        # La anterior no se borra: podía ser la imagen de otra vitrina o de un producto
        if input.image is not None:
            updates["image"] = _imagen(input.image)

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

        # Vitrinas antiguas pueden apuntar a imágenes ajenas: solo se borra la de su carpeta
        if showcase.image and clave_en_carpeta(showcase.image, "showcases"):
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
