"""GraphQL queries for Combo entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import combos_repo
from schema.combos.types import ComboType, combo_to_type


@strawberry.type
class ComboQuery:
    @strawberry.field(description="Obtener un combo por ID")
    async def combo(self, combo_id: str) -> Optional[ComboType]:
        """Obtiene un combo específico por su ID."""
        combo = await combos_repo.get_by_id(combo_id)
        if combo:
            return combo_to_type(combo)
        return None

    @strawberry.field(description="Obtener todos los combos de una sucursal")
    async def combos_by_branch(
        self, branch_id: str, available_only: bool = True
    ) -> List[ComboType]:
        """
        Obtiene todos los combos de una sucursal.
        Por defecto solo devuelve combos disponibles.
        """
        combos = await combos_repo.get_by_branch(branch_id, available_only)
        return [combo_to_type(combo) for combo in combos]

    @strawberry.field(description="Obtener todos los combos")
    async def all_combos(
        self,
        available_only: bool = False,
        branch_tipo: Optional[str] = None,
        product_category_id: Optional[str] = None,
        first: int = 50,
    ) -> List[ComboType]:
        """
        Obtiene todos los combos del sistema.
        Puede filtrar por tipo de negocio y categoría de producto.

        Args:
            available_only: Solo combos disponibles
            branch_tipo: Filtrar por tipo de negocio (restaurante, tienda, dulceria, etc.)
            product_category_id: Filtrar por categoría de producto
            first: Límite de resultados (máx 100, default 50)
        """
        first = min(first, 100)

        if branch_tipo or product_category_id:
            combos = await combos_repo.get_filtered(
                available_only=available_only,
                branch_tipo=branch_tipo,
                product_category_id=product_category_id,
            )
        else:
            combos = await combos_repo.get_all(available_only)

        return [combo_to_type(combo) for combo in combos[:first]]
