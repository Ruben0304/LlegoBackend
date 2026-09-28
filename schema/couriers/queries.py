"""GraphQL queries for courier verification."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from domain.orders import CourierVerificationStatus
from repositories import branches_repo, businesses_repo
from repositories.orders_repository import delivery_persons_repo
from utils.graphql_auth import require_auth, require_role

from .types import (
    CourierBranchType,
    CourierProfileType,
    CouriersConnectionType,
    CourierVerificationStatusEnum,
    courier_to_type,
    couriers_to_types,
)

ADMIN_ROLES = ["admin", "manager"]


@strawberry.type
class CourierQuery:
    @strawberry.field(
        description="Perfil y estado de verificación del mensajero autenticado"
    )
    async def my_courier_profile(self, info: Info, jwt: str) -> CourierProfileType:
        from schema.orders.queries import _get_or_create_delivery_person

        user_id = require_auth(jwt, info)
        delivery_person = await _get_or_create_delivery_person(user_id)
        return await courier_to_type(delivery_person)

    @strawberry.field(
        description="(Admin) Mensajeros filtrados por estado de verificación"
    )
    async def admin_couriers(
        self,
        info: Info,
        jwt: str,
        status: Optional[CourierVerificationStatusEnum] = None,
        search: Optional[str] = None,
        page: int = 1,
        pageSize: int = 20,
    ) -> CouriersConnectionType:
        require_role(jwt, info, ADMIN_ROLES)

        safe_page = max(1, page)
        safe_size = max(1, min(pageSize, 50))
        couriers, total = await delivery_persons_repo.list_for_admin(
            status=CourierVerificationStatus(status.value) if status else None,
            search=search,
            skip=(safe_page - 1) * safe_size,
            limit=safe_size,
        )
        seen = (safe_page - 1) * safe_size + len(couriers)
        return CouriersConnectionType(
            rows=await couriers_to_types(couriers),
            totalCount=total,
            hasMore=seen < total,
        )

    @strawberry.field(description="(Admin) Detalle de un mensajero")
    async def admin_courier(
        self, info: Info, jwt: str, courierId: str
    ) -> Optional[CourierProfileType]:
        require_role(jwt, info, ADMIN_ROLES)
        dp = await delivery_persons_repo.get_by_id(courierId)
        return await courier_to_type(dp) if dp else None

    @strawberry.field(
        description="(Admin) Sucursales activas que se pueden asignar a un mensajero"
    )
    async def admin_courier_branch_options(
        self, info: Info, jwt: str, search: Optional[str] = None
    ) -> List[CourierBranchType]:
        require_role(jwt, info, ADMIN_ROLES)

        branches = [
            b
            for b in await branches_repo.get_all()
            if b.isActive and b.useAppMessaging and not b.catalogOnly
        ]
        business_ids = list({str(b.businessId) for b in branches})
        businesses = await businesses_repo.get_by_ids(business_ids) if business_ids else []
        business_names = {str(b.id): b.name for b in businesses}

        options = [
            CourierBranchType(
                id=str(b.id),
                name=b.name,
                address=b.address,
                businessId=str(b.businessId),
                businessName=business_names.get(str(b.businessId)),
            )
            for b in branches
        ]
        if search:
            needle = search.strip().lower()
            options = [
                o
                for o in options
                if needle in o.name.lower()
                or needle in (o.businessName or "").lower()
                or needle in (o.address or "").lower()
            ]
        return sorted(options, key=lambda o: ((o.businessName or "").lower(), o.name.lower()))
