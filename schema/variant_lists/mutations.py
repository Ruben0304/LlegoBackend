"""GraphQL mutations for VariantList entity."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import variant_lists_repo
from schema.variant_lists.inputs import CreateVariantListInput, UpdateVariantListInput
from schema.variant_lists.types import VariantListType, variant_list_to_type
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class VariantListMutation:
    @strawberry.mutation(description="Crear una nueva lista de variantes")
    async def create_variant_list(
        self, info: Info, input: CreateVariantListInput, jwt: Optional[str] = None
    ) -> VariantListType:
        """
        Crea una nueva lista de variantes global para un negocio.
        Solo el propietario del negocio puede crear listas.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verificar acceso a la sucursal (solo propietario)
        await access_checker.require_branch_access(
            user_id, input.branchId, require_owner=True
        )

        # Validar que haya al menos una opción
        if not input.options:
            raise Exception("La lista de variantes debe tener al menos una opción")

        # Preparar datos
        variant_list_data = {
            "branchId": input.branchId,
            "name": input.name,
            "description": input.description,
            "options": [
                {
                    "id": opt.id,  # Si es None, el repo generará UUID
                    "name": opt.name,
                    "priceAdjustment": opt.priceAdjustment,
                }
                for opt in input.options
            ],
        }

        # Crear lista de variantes
        variant_list = await variant_lists_repo.create(variant_list_data)

        return variant_list_to_type(variant_list)

    @strawberry.mutation(description="Actualizar una lista de variantes existente")
    async def update_variant_list(
        self, info: Info, input: UpdateVariantListInput, jwt: Optional[str] = None
    ) -> VariantListType:
        """Actualiza una lista de variantes existente."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener lista existente
        variant_list = await variant_lists_repo.get_by_id(input.variantListId)
        if not variant_list:
            raise Exception("Lista de variantes no encontrada")

        # Verificar acceso a la sucursal (solo propietario)
        await access_checker.require_branch_access(
            user_id, str(variant_list.branchId), require_owner=True
        )

        # Preparar datos de actualización
        update_data = {}

        if input.name is not None:
            update_data["name"] = input.name

        if input.description is not None:
            update_data["description"] = input.description

        if input.options is not None:
            # Validar que haya al menos una opción
            if not input.options:
                raise Exception("La lista de variantes debe tener al menos una opción")

            update_data["options"] = [
                {
                    "id": opt.id,  # Si es None, el repo generará UUID
                    "name": opt.name,
                    "priceAdjustment": opt.priceAdjustment,
                }
                for opt in input.options
            ]

        if not update_data:
            raise Exception("No hay campos para actualizar")

        # Actualizar
        updated_variant_list = await variant_lists_repo.update(
            input.variantListId, update_data
        )
        if not updated_variant_list:
            raise Exception("Error al actualizar la lista de variantes")

        return variant_list_to_type(updated_variant_list)

    @strawberry.mutation(description="Eliminar una lista de variantes")
    async def delete_variant_list(
        self, info: Info, variant_list_id: str, jwt: Optional[str] = None
    ) -> bool:
        """Elimina una lista de variantes."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener lista existente
        variant_list = await variant_lists_repo.get_by_id(variant_list_id)
        if not variant_list:
            raise Exception("Lista de variantes no encontrada")

        # Verificar acceso a la sucursal (solo propietario)
        await access_checker.require_branch_access(
            user_id, str(variant_list.branchId), require_owner=True
        )

        # Quitar la referencia de todos los productos que la tengan
        from repositories import products_repo
        await products_repo.remove_variant_list_from_products(variant_list_id)

        # Eliminar
        deleted = await variant_lists_repo.delete(variant_list_id)
        if not deleted:
            raise Exception("Error al eliminar la lista de variantes")

        return True
