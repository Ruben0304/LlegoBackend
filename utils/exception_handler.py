"""Global exception handler for capturing and logging all unhandled exceptions."""
import traceback
import asyncio
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse

from services.error_analysis_service import sanitize_sensitive_data
from domain.error_logs import ErrorSource


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header (common with proxies/load balancers)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    
    # Fall back to direct client
    if request.client:
        return request.client.host
    
    return "unknown"


def get_user_id_from_request(request: Request) -> Optional[str]:
    """Try to extract user ID from request context."""
    # Check if user_id was set in request state (by auth middleware)
    if hasattr(request.state, "user_id"):
        return request.state.user_id
    
    # Try to get from GraphQL context if available
    if hasattr(request.state, "context") and isinstance(request.state.context, dict):
        return request.state.context.get("user_id")
    
    return None


async def log_exception(
    request: Request,
    exc: Exception,
    status_code: int = 500
) -> str:
    """Log exception to database and trigger background analysis."""
    # Import here to avoid circular imports at module load time
    from repositories.error_log_repository import error_log_repo
    from services.error_analysis_service import error_analysis_service
    
    # Build stack trace
    stack_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    sanitized_stack = sanitize_sensitive_data(stack_trace)

    # Extract request info
    error_data = {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "stack_trace": sanitized_stack,
        "endpoint": str(request.url.path),
        "http_method": request.method,
        "client_ip": get_client_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "user_id": get_user_id_from_request(request),
        "source": ErrorSource.BACKEND.value
    }

    # Save to database
    error_log = await error_log_repo.create(error_data)

    # Schedule background analysis (fire and forget)
    asyncio.create_task(
        error_analysis_service.analyze_and_update(error_log.id, error_data)
    )

    return error_log.id


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler that captures all unhandled exceptions.
    Logs to MongoDB and triggers Claude analysis in background.
    """
    try:
        error_id = await log_exception(request, exc)
        
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Error interno del servidor",
                "error_id": error_id
            }
        )
    except Exception as log_error:
        # If logging fails, still return error response
        print(f"Failed to log exception: {log_error}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    """
    Handler for HTTPException that logs 5xx errors.
    4xx errors are not logged as they are typically client errors.
    """
    from fastapi import HTTPException
    
    if isinstance(exc, HTTPException):
        # Only log server errors (5xx)
        if exc.status_code >= 500:
            try:
                await log_exception(request, exc, exc.status_code)
            except Exception as log_error:
                print(f"Failed to log HTTP exception: {log_error}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # Fallback for non-HTTPException
    return await global_exception_handler(request, exc)
