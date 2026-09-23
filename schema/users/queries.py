"""GraphQL query resolvers for User entity."""

from datetime import datetime, timedelta
from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import users_repo
from schema.wallet.types import WalletBalanceType
from services.user_metrics import build_segment_spec, compute_user_segments
from utils.graphql_auth import apply_optional_jwt, require_auth, require_role
from utils.serialization import to_strawberry_dict

from .types import (
    AdminUserRowType,
    AdminUsersConnectionType,
    DailyCountType,
    UserMetricsType,
    UserSegmentEnum,
    UserSegmentMetricsType,
    UserType,
)


@strawberry.type
class UserQuery:
    @strawberry.field(description="Lista de usuarios (requiere rol admin o manager)")
    async def users(self, info: Info, jwt: str) -> List[UserType]:
        """List all users. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        users = await users_repo.get_all()
        return [
            UserType(
                **{
                    **to_strawberry_dict(
                        u,
                        exclude={
                            "password",
                            "location",
                            "wallet",
                            "walletStatus",
                            "isPro",
                            "aiConsultasLimit",
                        },
                    ),
                    "wallet": WalletBalanceType(
                        local=u.wallet.get("local", 0.0), usd=u.wallet.get("usd", 0.0)
                    ),
                    "walletStatus": u.walletStatus,
                }
            )
            for u in users
        ]

    @strawberry.field(
        description=(
            "(Admin) Métricas de usuarios de la plataforma, segmentadas por app. "
            "Los segmentos se solapan: un mensajero o dueño de negocio también "
            "puede pedir como cliente."
        )
    )
    async def admin_user_metrics(
        self, info: Info, jwt: str, activeDays: int = 30
    ) -> UserMetricsType:
        require_role(jwt, info, ["admin", "manager"])

        window_days = max(1, activeDays)
        since = datetime.utcnow() - timedelta(days=window_days)

        sources = await users_repo.get_metrics_sources(since)
        segments = compute_user_segments(
            total_users=sources["total_users"],
            courier_ids=sources["courier_ids"],
            business_ids=sources["business_ids"],
            active_ids=sources["active_ids"],
        )
        signups = await users_repo.get_signups_by_day(since)

        return UserMetricsType(
            totalUsers=segments["totalUsers"],
            activeUsers=segments["activeUsers"],
            newUsersInPeriod=sources["new_users"],
            customersOnly=UserSegmentMetricsType(**segments["customersOnly"]),
            couriers=UserSegmentMetricsType(**segments["couriers"]),
            businesses=UserSegmentMetricsType(**segments["businesses"]),
            multiRoleUsers=segments["multiRoleUsers"],
            signupsByDay=[DailyCountType(**row) for row in signups],
            activeDays=window_days,
        )

    @strawberry.field(
        description=(
            "(Admin) Usuarios de un segmento concreto de admin_user_metrics, "
            "paginados. Permite abrir la lista detrás de cada tarjeta."
        )
    )
    async def admin_segment_users(
        self,
        info: Info,
        jwt: str,
        segment: UserSegmentEnum = UserSegmentEnum.ALL,
        activeDays: int = 30,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUsersConnectionType:
        require_role(jwt, info, ["admin", "manager"])

        window_days = max(1, activeDays)
        since = datetime.utcnow() - timedelta(days=window_days)

        # Same sources as the cards, so a list can never disagree with its count.
        sources = await users_repo.get_metrics_sources(since)
        spec = build_segment_spec(
            segment.value,
            courier_ids=sources["courier_ids"],
            business_ids=sources["business_ids"],
            active_ids=sources["active_ids"],
        )
        users, total = await users_repo.list_segment(
            spec=spec,
            since=since,
            search=search,
            limit=max(1, min(limit, 200)),
            offset=max(0, offset),
        )

        courier_ids = sources["courier_ids"]
        business_ids = sources["business_ids"]
        active_ids = sources["active_ids"]

        rows = []
        for u in users:
            uid = str(u.id)
            rows.append(
                AdminUserRowType(
                    id=uid,
                    name=u.name,
                    email=u.email,
                    username=u.username,
                    phone=u.phone,
                    createdAt=u.createdAt,
                    lastSeenAt=u.lastSeenAt,
                    authProvider=u.authProvider,
                    walletStatus=u.walletStatus,
                    deliveredOrdersCount=u.deliveredOrdersCount,
                    scheduledDeletionAt=u.scheduledDeletionAt,
                    isCourier=uid in courier_ids,
                    isBusiness=uid in business_ids,
                    isActive=uid in active_ids,
                    _avatar_path=u.avatar,
                )
            )

        return AdminUsersConnectionType(
            rows=rows,
            totalCount=total,
            hasMore=(offset + len(rows)) < total,
        )

    @strawberry.field(
        description="Obtener usuario por ID (requiere rol admin o manager)"
    )
    async def user(self, info: Info, id: str, jwt: str) -> Optional[UserType]:
        """Get user by ID. Requires admin or manager role."""
        require_role(jwt, info, ["admin", "manager"])
        user = await users_repo.get_by_id(id)
        if not user:
            return None
        return UserType(
            **{
                **to_strawberry_dict(
                    user,
                    exclude={
                        "password",
                        "location",
                        "wallet",
                        "walletStatus",
                        "isPro",
                        "aiConsultasLimit",
                    },
                ),
                "wallet": WalletBalanceType(
                    local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
                ),
                "walletStatus": user.walletStatus,
            }
        )

    @strawberry.field(description="Buscar usuarios (requiere autenticación)")
    async def search_users(self, info: Info, query: str, jwt: str) -> List[UserType]:
        """Search users. Requires authentication."""
        require_auth(jwt, info)
        users = await users_repo.search(query)
        return [
            UserType(
                **{
                    **to_strawberry_dict(
                        u,
                        exclude={
                            "password",
                            "location",
                            "wallet",
                            "walletStatus",
                            "isPro",
                            "aiConsultasLimit",
                        },
                    ),
                    "wallet": WalletBalanceType(
                        local=u.wallet.get("local", 0.0), usd=u.wallet.get("usd", 0.0)
                    ),
                    "walletStatus": u.walletStatus,
                }
            )
            for u in users
        ]

    @strawberry.field(description="Usuario actual desde JWT")
    async def me(self, info: Info, jwt: str) -> Optional[UserType]:
        """Get current authenticated user."""
        user_id = require_auth(jwt, info)
        user = await users_repo.get_by_id(user_id)
        if not user:
            return None
        return UserType(
            **{
                **to_strawberry_dict(
                    user,
                    exclude={
                        "password",
                        "location",
                        "wallet",
                        "walletStatus",
                        "isPro",
                        "aiConsultasLimit",
                    },
                ),
                "wallet": WalletBalanceType(
                    local=user.wallet.get("local", 0.0), usd=user.wallet.get("usd", 0.0)
                ),
                "walletStatus": user.walletStatus,
            }
        )
