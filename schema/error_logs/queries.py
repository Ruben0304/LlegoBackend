"""GraphQL query resolvers for the admin error inbox."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories.error_log_repository import error_log_repo
from utils.graphql_auth import require_role

from .types import (
    ErrorLogsConnectionType,
    ErrorSeverityEnum,
    ErrorSourceEnum,
    ErrorStatsType,
    buckets_to_types,
    error_log_to_type,
)


@strawberry.type
class ErrorLogQuery:
    @strawberry.field(
        description=(
            "(Admin) Bandeja de errores: backend y apps, con el análisis de IA "
            "de cada uno. Paginada y filtrable."
        )
    )
    async def admin_error_logs(
        self,
        info: Info,
        jwt: str,
        page: int = 1,
        pageSize: int = 20,
        days: Optional[int] = None,
        source: Optional[ErrorSourceEnum] = None,
        severity: Optional[ErrorSeverityEnum] = None,
        resolved: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> ErrorLogsConnectionType:
        require_role(jwt, info, ["admin", "manager"])

        safe_page = max(1, page)
        safe_size = max(1, min(pageSize, 100))

        logs, total = await error_log_repo.get_paginated(
            page=safe_page,
            page_size=safe_size,
            days=days,
            source=source.value if source else None,
            severity=severity.value if severity else None,
            resolved=resolved,
            search=search,
        )

        seen = (safe_page - 1) * safe_size + len(logs)
        return ErrorLogsConnectionType(
            rows=[error_log_to_type(log) for log in logs],
            totalCount=total,
            hasMore=seen < total,
        )

    @strawberry.field(
        description="(Admin) Resumen de errores del periodo: totales, severidad, fuente y tipos más frecuentes"
    )
    async def admin_error_stats(
        self, info: Info, jwt: str, days: int = 7
    ) -> ErrorStatsType:
        require_role(jwt, info, ["admin", "manager"])

        stats = await error_log_repo.get_stats(days=max(1, days))
        return ErrorStatsType(
            totalErrors=stats["total_errors"],
            resolvedErrors=stats["resolved_errors"],
            pendingErrors=stats["pending_errors"],
            criticalUnresolved=stats["critical_unresolved"],
            periodDays=stats["period_days"],
            bySeverity=buckets_to_types(stats["by_severity"]),
            bySource=buckets_to_types(stats["by_source"]),
            byType=buckets_to_types(stats["by_type"]),
        )
