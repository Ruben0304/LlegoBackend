"""REST endpoints for error logging system."""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Optional
from math import ceil
import logging

from models_error_logs import (
    MobileErrorReport,
    ErrorLogResponse,
    PaginatedErrorLogs,
    ErrorStats,
    ErrorSource
)
from repositories.error_log_repository import error_log_repo
from services.error_analysis_service import error_analysis_service, sanitize_sensitive_data

router = APIRouter(prefix="/api/error-logs", tags=["Error Logs"])
logger = logging.getLogger(__name__)


def _to_response(error_log) -> ErrorLogResponse:
    """Convert ErrorLog model to response schema."""
    return ErrorLogResponse(
        id=error_log.id,
        error_type=error_log.error_type,
        error_message=error_log.error_message,
        stack_trace=error_log.stack_trace,
        endpoint=error_log.endpoint,
        http_method=error_log.http_method,
        client_ip=error_log.client_ip,
        user_agent=error_log.user_agent,
        user_id=error_log.user_id,
        source=error_log.source.value if hasattr(error_log.source, 'value') else error_log.source,
        app_version=error_log.app_version,
        device_info=error_log.device_info,
        screen=error_log.screen,
        action=error_log.action,
        extra_data=error_log.extra_data,
        gemini_analysis=error_log.gemini_analysis,
        resolved=error_log.resolved,
        resolved_at=error_log.resolved_at,
        resolved_by=error_log.resolved_by,
        occurrence_count=error_log.occurrence_count,
        last_occurrence_at=error_log.last_occurrence_at,
        created_at=error_log.created_at
    )


@router.get("/", response_model=PaginatedErrorLogs)
async def list_error_logs(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(20, ge=1, le=100, description="Elementos por página"),
    days: Optional[int] = Query(None, ge=1, description="Filtrar últimos N días"),
    source: Optional[str] = Query(None, description="Filtrar por fuente: backend, mobile_android, mobile_ios, web"),
    severity: Optional[str] = Query(None, description="Filtrar por severidad: baja, media, alta, critica"),
    resolved: Optional[bool] = Query(None, description="Filtrar por estado resuelto"),
    search: Optional[str] = Query(None, description="Buscar en tipo, mensaje o endpoint")
):
    """List error logs with pagination and filters."""
    logs, total = await error_log_repo.get_paginated(
        page=page,
        page_size=page_size,
        days=days,
        source=source,
        severity=severity,
        resolved=resolved,
        search=search
    )

    total_pages = ceil(total / page_size) if total > 0 else 1

    return PaginatedErrorLogs(
        items=[_to_response(log) for log in logs],
        total_items=total,
        total_pages=total_pages,
        page=page,
        page_size=page_size
    )


@router.get("/stats", response_model=ErrorStats)
async def get_error_stats(
    days: int = Query(7, ge=1, le=365, description="Período en días para estadísticas")
):
    """Get error statistics for the last N days."""
    stats = await error_log_repo.get_stats(days=days)
    return ErrorStats(**stats)


@router.get("/{error_id}", response_model=ErrorLogResponse)
async def get_error_log(error_id: str):
    """Get a specific error log by ID."""
    error_log = await error_log_repo.get_by_id(error_id)
    if not error_log:
        raise HTTPException(status_code=404, detail="Error log no encontrado")
    return _to_response(error_log)


@router.post("/mobile-report", response_model=ErrorLogResponse, status_code=201)
async def report_mobile_error(
    report: MobileErrorReport,
    background_tasks: BackgroundTasks
):
    """Endpoint for mobile apps to report errors."""
    logger.info(f"="*80)
    logger.info(f"📥 MOBILE ERROR RECEIVED")
    logger.info(f"Error type: {report.error_type}")
    logger.info(f"Error message: {report.error_message[:100]}")
    logger.info(f"Source: {report.source}")
    logger.info(f"="*80)

    # Sanitize stack trace
    sanitized_stack = sanitize_sensitive_data(report.stack_trace) if report.stack_trace else None

    # Normalize error_message (trim whitespace, consistent format)
    normalized_message = report.error_message.strip()

    try:
        # Check if there's a similar pending error
        logger.info(f"🔍 Checking for duplicates...")
        existing_error = await error_log_repo.find_similar_pending(
            error_type=report.error_type.strip(),
            error_message=normalized_message,
            source=report.source
        )

        if existing_error:
            # Increment occurrence count instead of creating new error
            logger.warning(f"🔁 DUPLICATE FOUND! Error ID: {existing_error.id}")
            await error_log_repo.increment_occurrence(existing_error.id)
            # Fetch updated error to return correct count
            updated_error = await error_log_repo.get_by_id(existing_error.id)
            logger.info(f"✅ Count incremented to {updated_error.occurrence_count}")
            logger.info(f"🚫 Skipping Gemini analysis and notification")
            return _to_response(updated_error)

        logger.info(f"✨ NEW ERROR - Creating entry")

        # No duplicate found - create new error
        error_data = {
            "error_type": report.error_type.strip(),
            "error_message": normalized_message,
            "stack_trace": sanitized_stack,
            "source": report.source,
            "app_version": report.app_version,
            "device_info": report.device_info,
            "screen": report.screen,
            "action": report.action,
            "extra_data": report.extra_data
        }

        error_log = await error_log_repo.create(error_data)
        logger.info(f"✅ Error created with ID: {error_log.id}")

        # Schedule background analysis only for NEW errors
        logger.info(f"📤 Scheduling Gemini analysis and notification")
        background_tasks.add_task(
            error_analysis_service.analyze_and_update,
            error_log.id,
            error_data
        )

        return _to_response(error_log)

    except Exception as e:
        logger.error(f"❌ ERROR in report_mobile_error: {e}", exc_info=True)
        raise


@router.patch("/{error_id}/resolve")
async def resolve_error(error_id: str, resolved_by: Optional[str] = None):
    """Mark an error as resolved."""
    error_log = await error_log_repo.get_by_id(error_id)
    if not error_log:
        raise HTTPException(status_code=404, detail="Error log no encontrado")

    success = await error_log_repo.mark_resolved(error_id, resolved_by)
    if not success:
        raise HTTPException(status_code=500, detail="Error al actualizar")

    return {"message": "Error marcado como resuelto", "id": error_id}


@router.patch("/{error_id}/unresolve")
async def unresolve_error(error_id: str):
    """Reopen an error (mark as unresolved)."""
    error_log = await error_log_repo.get_by_id(error_id)
    if not error_log:
        raise HTTPException(status_code=404, detail="Error log no encontrado")

    success = await error_log_repo.mark_unresolved(error_id)
    if not success:
        raise HTTPException(status_code=500, detail="Error al actualizar")

    return {"message": "Error reabierto", "id": error_id}


@router.delete("/cleanup")
async def cleanup_old_errors(
    days: int = Query(30, ge=7, description="Eliminar errores resueltos más antiguos que N días")
):
    """Delete old resolved error logs."""
    deleted_count = await error_log_repo.cleanup_old_resolved(days=days)
    return {
        "message": f"Limpieza completada",
        "deleted_count": deleted_count,
        "criteria": f"Errores resueltos con más de {days} días"
    }


@router.post("/test-push/clientes")
async def test_push_clientes():
    """Test push notification to Llego Clientes app (com.ruben.LlegoiOS)."""
    from services.push_notification_service import push_service
    from repositories.device_token_repository import device_token_repo
    
    bundle_id = "com.ruben.LlegoiOS"
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    if not ios_tokens:
        return {"error": "No iOS tokens registered", "bundle_id": bundle_id}
    
    result = await push_service.send_to_all(
        tokens=ios_tokens,
        title="🧪 Test Clientes",
        body="Notificación de prueba para Llego Clientes",
        data={"type": "test"},
        platform="IOS",
        bundle_id=bundle_id
    )
    
    return {"bundle_id": bundle_id, "tokens": len(ios_tokens), "result": result}


@router.post("/test-push/negocios")
async def test_push_negocios():
    """Test push notification to Llego Negocios app (com.llego.business.LlegoBusiness)."""
    from services.push_notification_service import push_service
    from repositories.device_token_repository import device_token_repo
    
    bundle_id = "com.llego.business.LlegoBusiness"
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    if not ios_tokens:
        return {"error": "No iOS tokens registered", "bundle_id": bundle_id}
    
    result = await push_service.send_to_all(
        tokens=ios_tokens,
        title="🧪 Test Negocios",
        body="Notificación de prueba para Llego Negocios",
        data={"type": "test"},
        platform="IOS",
        bundle_id=bundle_id
    )
    
    return {"bundle_id": bundle_id, "tokens": len(ios_tokens), "result": result}
