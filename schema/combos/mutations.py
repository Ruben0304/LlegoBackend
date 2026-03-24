"""GraphQL mutations for Combo entity."""

from typing import Any, Dict, List, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, combos_repo, products_repo
from schema.combos.inputs import CreateComboInput, UpdateComboInput
from schema.combos.types import ComboType, combo_to_type
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class ComboMutation:
    @staticmethod
    def _normalize_currency(value: Optional[str], fallback: str = "USD") -> str:
        normalized = (value or "").strip().upper()
        if normalized in {"USD", "CUP"}:
            return normalized
        return fallback

    @staticmethod
    def _validate_discount(discount_type: str, discount_value: float) -> None:
        dt = (discount_type or "none").strip().lower()
        dv = float(discount_value or 0.0)

        if dt == "none":
            if dv != 0:
                raise Exception(
                    "Cuando discountType es 'none', discountValue debe ser 0"
                )
            return

        if dt == "percentage":
            if dv < 0 or dv > 100:
                raise Exception("discountValue para porcentaje debe estar entre 0 y 100")
            return

        if dt == "fixed":
            if dv < 0:
                raise Exception("discountValue para descuento fijo no puede ser negativo")
            return

        raise Exception(f"Tipo de descuento no soportado: {discount_type}")

    @staticmethod
    async def _validate_and_prepare_slots(
        slots: List[Any],
        branch_id: str,
    ) -> tuple[List[Dict[str, Any]], str]:
        if not slots:
            raise Exception("El combo debe tener al menos un slot")

        prepared_slots: List[Dict[str, Any]] = []
        product_cache: Dict[str, Any] = {}
        currencies = set()

        for slot in slots:
            if not slot.options:
                raise Exception(f"El slot '{slot.name}' debe tener al menos una opciÃ³n")

            min_sel = int(slot.minSelections)
            max_sel = int(slot.maxSelections)

            if min_sel < 0:
                raise Exception(
                    f"El slot '{slot.name}' no puede tener minSelections negativo"
                )
            if max_sel <= 0:
                raise Exception(
                    f"El slot '{slot.name}' debe tener maxSelections mayor que 0"
                )
            if max_sel < min_sel:
                raise Exception(
                    f"El slot '{slot.name}' tiene maxSelections menor que minSelections"
                )
            if slot.isRequired and min_sel == 0:
                raise Exception(
                    f"El slot '{slot.name}' es requerido, minSelections debe ser mayor que 0"
                )
            if max_sel > len(slot.options):
                raise Exception(
                    f"El slot '{slot.name}' permite mÃ¡s selecciones que opciones disponibles"
                )

            default_count = sum(1 for opt in slot.options if opt.isDefault)
            if default_count > max_sel:
                raise Exception(
                    f"El slot '{slot.name}' tiene mÃ¡s opciones por defecto que maxSelections"
                )
            if slot.isRequired and min_sel > 0 and default_count == 0:
                raise Exception(
                    f"El slot '{slot.name}' requiere al menos una opciÃ³n por defecto"
                )

            seen_product_ids = set()
            prepared_options = []
            for opt in slot.options:
                product_id = str(opt.productId)
                if product_id in seen_product_ids:
                    raise Exception(
                        f"El slot '{slot.name}' tiene productos duplicados: {product_id}"
                    )
                seen_product_ids.add(product_id)

                product = product_cache.get(product_id)
                if not product:
                    product = await products_repo.get_by_id(product_id)
                    if not product:
                        raise Exception(f"Producto {product_id} no encontrado")
                    product_cache[product_id] = product

                if str(product.branchId) != str(branch_id):
                    raise Exception(
                        f"Producto {product.name} no pertenece a la sucursal del combo"
                    )

                currencies.add(
                    ComboMutation._normalize_currency(
                        getattr(product, "currency", None)
                    )
                )

                seen_modifiers = set()
                prepared_modifiers = []
                for mod in opt.availableModifiers:
                    mod_name = (mod.name or "").strip()
                    if not mod_name:
                        raise Exception(
                            f"Un modificador en slot '{slot.name}' no tiene nombre"
                        )
                    mod_key = mod_name.lower()
                    if mod_key in seen_modifiers:
                        raise Exception(
                            f"Modificador duplicado '{mod_name}' en slot '{slot.name}'"
                        )
                    seen_modifiers.add(mod_key)
                    prepared_modifiers.append(
                        {
                            "name": mod_name,
                            "priceAdjustment": float(mod.priceAdjustment or 0.0),
                        }
                    )

                prepared_options.append(
                    {
                        "productId": product_id,
                        "isDefault": bool(opt.isDefault),
                        "priceAdjustment": float(opt.priceAdjustment or 0.0),
                        "availableModifiers": prepared_modifiers,
                    }
                )

            prepared_slots.append(
                {
                    "name": slot.name,
                    "description": slot.description,
                    "options": prepared_options,
                    "minSelections": min_sel,
                    "maxSelections": max_sel,
                    "isRequired": bool(slot.isRequired),
                    "displayOrder": int(slot.displayOrder),
                }
            )

        if len(currencies) > 1:
            raise Exception(
                "Todos los productos del combo deben usar la misma moneda (USD o CUP)"
            )

        if currencies:
            combo_currency = next(iter(currencies))
        else:
            branch = await branches_repo.get_by_id(branch_id)
            combo_currency = "CUP" if getattr(branch, "acceptedCurrency", None) == "CUP" else "USD"

        return prepared_slots, combo_currency

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

        # Validar slots/productos y descuento
        slots_payload, combo_currency = await ComboMutation._validate_and_prepare_slots(
            slots=input.slots,
            branch_id=input.branchId,
        )
        ComboMutation._validate_discount(input.discountType.value, input.discountValue)

        combo_data = {
            "branchId": input.branchId,
            "name": input.name,
            "description": input.description,
            "image": input.image,
            "slots": slots_payload,
            "discountType": input.discountType.value,
            "discountValue": float(input.discountValue or 0.0),
            "currency": combo_currency,
            "availability": True,
            "categoryId": input.categoryId,
        }

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
            slots_payload, combo_currency = await ComboMutation._validate_and_prepare_slots(
                slots=input.slots,
                branch_id=str(combo.branchId),
            )
            update_data["slots"] = slots_payload
            update_data["currency"] = combo_currency

        final_discount_type = (
            input.discountType.value if input.discountType is not None else combo.discountType
        )
        final_discount_value = (
            float(input.discountValue)
            if input.discountValue is not None
            else float(combo.discountValue or 0.0)
        )
        if final_discount_type == "none":
            final_discount_value = 0.0
        ComboMutation._validate_discount(final_discount_type, final_discount_value)
        update_data["discountType"] = final_discount_type
        update_data["discountValue"] = final_discount_value

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
