"""GraphQL mutations for Combo entity."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import combos_repo
from schema.combos.inputs import CreateComboInput, UpdateComboInput
from schema.combos.types import ComboType, combo_to_type
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class ComboMutation:
    @strawberry.mutation(description="Crear un nuevo combo")
    async def create_combo(
        self, info: Info, input: CreateComboInput, jwt: Optional[str] = None
    ) -> ComboType:
        """
        Crea un nuevo combo personalizable.
        La imagen es opcional - si no se proporciona, el frontend generará una composición.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verificar acceso a la sucursal
        await access_checker.require_branch_access(user_id, input.branchId)

        # Validar que haya al menos un slot
        if not input.slots:
            raise Exception("El combo debe tener al menos un slot")

        # Validar cada slot
        for slot in input.slots:
            if not slot.options:
                raise Exception(f"El slot '{slot.name}' debe tener al menos una opción")

            if slot.minSelections < 0:
                raise Exception(
                    f"El slot '{slot.name}' no puede tener minSelections negativo"
                )

            if slot.maxSelections < slot.minSelections:
                raise Exception(
                    f"El slot '{slot.name}' tiene maxSelections menor que minSelections"
                )

        # Preparar datos
        combo_data = {
            "branchId": input.branchId,
            "name": input.name,
            "description": input.description,
            "image": input.image,
            "slots": [
                {
                    "name": slot.name,
                    "description": slot.description,
                    "options": [
                        {
                            "productId": opt.productId,
                            "isDefault": opt.isDefault,
                            "priceAdjustment": opt.priceAdjustment,
                            "availableModifiers": [
                                {"name": mod.name, "priceAdjustment": mod.priceAdjustment}
                                for mod in opt.availableModifiers
                            ],
                        }
                        for opt in slot.options
                    ],
                    "minSelections": slot.minSelections,
                    "maxSelections": slot.maxSelections,
                    "isRequired": slot.isRequired,
                    "displayOrder": slot.displayOrder,
                }
                for slot in input.slots
            ],
            "discountType": input.discountType.value,
            "discountValue": input.discountValue,
            "currency": "USD",
            "availability": True,
            "categoryId": input.categoryId,
        }

        # Crear combo
        combo = await combos_repo.create(combo_data)

        return combo_to_type(combo)

    @strawberry.mutation(description="Actualizar un combo existente")
    async def update_combo(
        self, info: Info, input: UpdateComboInput, jwt: Optional[str] = None
    ) -> ComboType:
        """Actualiza un combo existente."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener combo existente
        combo = await combos_repo.get_by_id(input.comboId)
        if not combo:
            raise Exception("Combo no encontrado")

        # Verificar acceso a la sucursal
        await access_checker.require_branch_access(user_id, combo.branchId)

        # Preparar datos de actualización
        update_data = {}

        if input.name is not None:
            update_data["name"] = input.name

        if input.description is not None:
            update_data["description"] = input.description

        if input.image is not None:
            update_data["image"] = input.image

        if input.slots is not None:
            # Validar slots
            if not input.slots:
                raise Exception("El combo debe tener al menos un slot")

            for slot in input.slots:
                if not slot.options:
                    raise Exception(f"El slot '{slot.name}' debe tener al menos una opción")

            update_data["slots"] = [
                {
                    "name": slot.name,
                    "description": slot.description,
                    "options": [
                        {
                            "productId": opt.productId,
                            "isDefault": opt.isDefault,
                            "priceAdjustment": opt.priceAdjustment,
                            "availableModifiers": [
                                {"name": mod.name, "priceAdjustment": mod.priceAdjustment}
                                for mod in opt.availableModifiers
                            ],
                        }
                        for opt in slot.options
                    ],
                    "minSelections": slot.minSelections,
                    "maxSelections": slot.maxSelections,
                    "isRequired": slot.isRequired,
                    "displayOrder": slot.displayOrder,
                }
                for slot in input.slots
            ]

        if input.discountType is not None:
            update_data["discountType"] = input.discountType.value

        if input.discountValue is not None:
            update_data["discountValue"] = input.discountValue

        if input.availability is not None:
            update_data["availability"] = input.availability

        if input.categoryId is not None:
            update_data["categoryId"] = input.categoryId

        # Actualizar
        updated_combo = await combos_repo.update(input.comboId, update_data)
        if not updated_combo:
            raise Exception("Error al actualizar el combo")

        return combo_to_type(updated_combo)

    @strawberry.mutation(description="Eliminar un combo")
    async def delete_combo(
        self, info: Info, combo_id: str, jwt: Optional[str] = None
    ) -> bool:
        """Elimina un combo."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener combo existente
        combo = await combos_repo.get_by_id(combo_id)
        if not combo:
            raise Exception("Combo no encontrado")

        # Verificar acceso a la sucursal
        await access_checker.require_branch_access(user_id, combo.branchId)

        # Eliminar
        deleted = await combos_repo.delete(combo_id)
        return deleted

    @strawberry.mutation(description="Cambiar disponibilidad de un combo")
    async def toggle_combo_availability(
        self, info: Info, combo_id: str, availability: bool, jwt: Optional[str] = None
    ) -> ComboType:
        """Activa o desactiva la disponibilidad de un combo."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener combo existente
        combo = await combos_repo.get_by_id(combo_id)
        if not combo:
            raise Exception("Combo no encontrado")

        # Verificar acceso a la sucursal
        await access_checker.require_branch_access(user_id, combo.branchId)

        # Actualizar disponibilidad
        await combos_repo.update_availability(combo_id, availability)

        # Obtener combo actualizado
        updated_combo = await combos_repo.get_by_id(combo_id)
        return combo_to_type(updated_combo)
