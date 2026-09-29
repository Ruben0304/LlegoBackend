"""GraphQL queries for push notifications sent from the Panel Admin."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import users_repo
from repositories.admin_push_repository import admin_push_repo
from repositories.device_token_repository import device_token_repo
from schema.business_types.types import DevicePlatformEnum
from services.admin_push import resolve_devices
from utils.graphql_auth import require_role

from .types import (
    AdminPushHistoryConnectionType,
    PushAudienceEnum,
    PushAudienceSizeType,
    PushDevicesConnectionType,
    PushRecipientsInput,
    device_to_type,
    notification_to_type,
    recipients_to_domain,
)

ADMIN_ROLES = ["admin", "manager"]


def _page(page: int, page_size: int) -> tuple[int, int]:
    safe_size = max(1, min(page_size, 50))
    return (max(1, page) - 1) * safe_size, safe_size


@strawberry.type
class AdminPushQuery:
    @strawberry.field(
        description=(
            "(Admin) Dispositivos con la app instalada y push activo, incluidos "
            "los que no tienen sesión iniciada"
        )
    )
    async def admin_push_devices(
        self,
        info: Info,
        jwt: str,
        audience: Optional[PushAudienceEnum] = None,
        platform: Optional[DevicePlatformEnum] = None,
        search: Optional[str] = None,
        userId: Optional[str] = None,
        anonymousOnly: bool = False,
        page: int = 1,
        pageSize: int = 20,
    ) -> PushDevicesConnectionType:
        require_role(jwt, info, ADMIN_ROLES)

        user_ids = None
        if userId:
            user_ids = [userId]
        elif search and search.strip() and not anonymousOnly:
            user_ids = [str(u.id) for u in await users_repo.search(search.strip())]
            if not user_ids:
                return PushDevicesConnectionType(rows=[], totalCount=0, hasMore=False)

        skip, limit = _page(page, pageSize)
        devices, total = await device_token_repo.list_for_admin(
            audience=audience.value if audience else None,
            platform=platform.value if platform else None,
            user_ids=user_ids,
            anonymous_only=anonymousOnly,
            skip=skip,
            limit=limit,
        )
        owners = await users_repo.get_by_ids(
            list({str(d.userId) for d in devices if d.userId})
        )
        users = {str(u.id): u for u in owners}
        return PushDevicesConnectionType(
            rows=[device_to_type(d, users) for d in devices],
            totalCount=total,
            hasMore=skip + len(devices) < total,
        )

    @strawberry.field(
        description="(Admin) Cuántos dispositivos recibirían un envío, antes de hacerlo"
    )
    async def admin_push_audience_size(
        self, info: Info, jwt: str, recipients: PushRecipientsInput
    ) -> PushAudienceSizeType:
        require_role(jwt, info, ADMIN_ROLES)
        try:
            devices = await resolve_devices(**recipients_to_domain(recipients))
        except ValueError as e:
            raise Exception(str(e))
        ios = sum(1 for d in devices if d.platform == "IOS")
        return PushAudienceSizeType(total=len(devices), ios=ios, android=len(devices) - ios)

    @strawberry.field(description="(Admin) Historial de notificaciones enviadas")
    async def admin_push_history(
        self, info: Info, jwt: str, page: int = 1, pageSize: int = 20
    ) -> AdminPushHistoryConnectionType:
        require_role(jwt, info, ADMIN_ROLES)
        skip, limit = _page(page, pageSize)
        rows, total = await admin_push_repo.list_recent(skip=skip, limit=limit)
        return AdminPushHistoryConnectionType(
            rows=[notification_to_type(n) for n in rows],
            totalCount=total,
            hasMore=skip + len(rows) < total,
        )
