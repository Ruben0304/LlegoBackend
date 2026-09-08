"""GraphQL type definitions for error logs (admin error inbox)."""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import strawberry


@strawberry.enum
class ErrorSeverityEnum(Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


@strawberry.enum
class ErrorSourceEnum(Enum):
    BACKEND = "backend"
    MOBILE_ANDROID = "mobile_android"
    MOBILE_IOS = "mobile_ios"
    WEB = "web"


@strawberry.type
class GeminiAnalysisType:
    """What the AI concluded about an error — see services/error_analysis_service."""

    resumen: str
    tipoError: str
    causaProbable: str
    soluciones: List[str]
    severidad: str
    requiereAccionInmediata: bool
    archivo: Optional[str] = None
    linea: Optional[int] = None


@strawberry.type
class ErrorLogType:
    id: str
    errorType: str
    errorMessage: str
    source: str
    resolved: bool
    occurrenceCount: int
    createdAt: datetime
    lastOccurrenceAt: Optional[datetime] = None
    stackTrace: Optional[str] = None
    endpoint: Optional[str] = None
    httpMethod: Optional[str] = None
    clientIp: Optional[str] = None
    userAgent: Optional[str] = None
    userId: Optional[str] = None
    appVersion: Optional[str] = None
    deviceInfo: Optional[str] = None
    screen: Optional[str] = None
    action: Optional[str] = None
    # JSON-encoded: shape is caller-defined, not worth a GraphQL type.
    extraDataJson: Optional[str] = None
    geminiAnalysis: Optional[GeminiAnalysisType] = None
    resolvedAt: Optional[datetime] = None
    resolvedBy: Optional[str] = None


@strawberry.type
class ErrorLogsConnectionType:
    rows: List[ErrorLogType]
    totalCount: int
    hasMore: bool


@strawberry.type
class ErrorCountByKeyType:
    """One bucket of the stats breakdown (severity, source or error type)."""

    key: str
    count: int


@strawberry.type
class ErrorStatsType:
    totalErrors: int
    resolvedErrors: int
    pendingErrors: int
    criticalUnresolved: int
    periodDays: int
    bySeverity: List[ErrorCountByKeyType]
    bySource: List[ErrorCountByKeyType]
    byType: List[ErrorCountByKeyType]


def _analysis_to_type(analysis) -> Optional[GeminiAnalysisType]:
    if not analysis:
        return None
    severity = getattr(analysis, "severidad", None)
    return GeminiAnalysisType(
        resumen=analysis.resumen,
        tipoError=analysis.tipo_error,
        causaProbable=analysis.causa_probable,
        soluciones=list(analysis.soluciones or []),
        severidad=getattr(severity, "value", severity) or "",
        requiereAccionInmediata=bool(analysis.requiere_accion_inmediata),
        archivo=analysis.archivo,
        linea=analysis.linea,
    )


def error_log_to_type(log) -> ErrorLogType:
    """Convert an ErrorLog domain model to its GraphQL type.

    Field by field on purpose: the domain model is snake_case while the schema
    is camelCase, and this keeps `stack_trace` and `client_ip` from being
    exposed by accident if the model grows.
    """
    source = getattr(log.source, "value", log.source)
    return ErrorLogType(
        id=str(log.id),
        errorType=log.error_type,
        errorMessage=log.error_message,
        source=source,
        resolved=bool(log.resolved),
        occurrenceCount=log.occurrence_count,
        createdAt=log.created_at,
        lastOccurrenceAt=log.last_occurrence_at,
        stackTrace=log.stack_trace,
        endpoint=log.endpoint,
        httpMethod=log.http_method,
        clientIp=log.client_ip,
        userAgent=log.user_agent,
        userId=str(log.user_id) if log.user_id else None,
        appVersion=log.app_version,
        deviceInfo=log.device_info,
        screen=log.screen,
        action=log.action,
        extraDataJson=json.dumps(log.extra_data) if log.extra_data else None,
        geminiAnalysis=_analysis_to_type(log.gemini_analysis),
        resolvedAt=log.resolved_at,
        resolvedBy=str(log.resolved_by) if log.resolved_by else None,
    )


def buckets_to_types(raw: Dict[str, Any]) -> List[ErrorCountByKeyType]:
    """Turn a {key: count} dict from the repo's $facet into a sorted list."""
    return [
        ErrorCountByKeyType(key=str(k), count=int(v))
        for k, v in sorted((raw or {}).items(), key=lambda kv: -kv[1])
    ]
