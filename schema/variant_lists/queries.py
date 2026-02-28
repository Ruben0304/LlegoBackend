"""GraphQL query resolvers for VariantList entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import variant_lists_repo
from schema.variant_lists.types import VariantListType, variant_list_to_type
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class VariantListQuery:
    @strawberry.field(description="Obtener listas de variantes por negocio")
    async def variant_lists(
        self, info: Info, business_id: str, jwt: Optional[str] = None
    ) -> List[VariantListType]:
        """
        Obtiene todas las listas de variantes de un negocio.
        Solo usuarios con acceso al negocio pueden ver sus listas.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verificar acceso al negocio
        await access_checker.require_business_access(user_id, business_id)

        # Obtener listas
        variant_lists = await variant_lists_repo.get_by_business(business_id)

        return [variant_list_to_type(vl) for vl in variant_lists]

    @strawberry.field(description="Obtener lista de variantes por ID")
    async def variant_list(
        self, info: Info, id: str, jwt: Optional[str] = None
    ) -> Optional[VariantListType]:
        """Obtiene una lista de variantes por su ID."""
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Obtener lista
        variant_list = await variant_lists_repo.get_by_id(id)
        if not variant_list:
            return None

        # Verificar acceso al negocio
        await access_checker.require_business_access(
            user_id, str(variant_list.businessId)
        )

        return variant_list_to_type(variant_list)
