"""GraphQL queries for Combo entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import combos_repo
from schema.combos.types import ComboType


@strawberry.type
class ComboQuery:
    @strawberry.field(description="Obtener un combo por ID")
    async def combo(self, combo_id: str) -> Optional[ComboType]:
        """Obtiene un combo específico por su ID."""
        combo = await combos_repo.get_by_id(combo_id)
        if combo:
            return ComboType(**combo.model_dump())
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
        return [ComboType(**combo.model_dump()) for combo in combos]

    @strawberry.field(description="Obtener todos los combos")
    async def all_combos(self, available_only: bool = False) -> List[ComboType]:
        """
        Obtiene todos los combos del sistema.
        Útil para administradores.
        """
        combos = await combos_repo.get_all(available_only)
        return [ComboType(**combo.model_dump()) for combo in combos]
