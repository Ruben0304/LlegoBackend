"""GraphQL query resolvers for promo requests (administrative app)."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import promo_requests_repo
from utils.graphql_auth import require_role

from .types import PromoRequestPage, promo_request_to_type


@strawberry.type
class PromoQuery:
    @strawberry.field(
        description=(
            "[Admin/Manager] Promos enviadas desde la app de cliente. "
            "Filtra por status: pending | approved | rejected."
        )
    )
    async def promo_requests(
        self,
        info: Info,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        jwt: Optional[str] = None,
    ) -> PromoRequestPage:
        require_role(jwt, info, ["admin", "manager"])

        if status is not None and status not in ("pending", "approved", "rejected"):
            raise Exception("status debe ser 'pending', 'approved' o 'rejected'")

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        requests = await promo_requests_repo.list_by_status(
            status=status, limit=limit, skip=offset
        )
        total = await promo_requests_repo.count_by_status(status=status)

        return PromoRequestPage(
            items=[promo_request_to_type(r) for r in requests],
            total=total,
        )
