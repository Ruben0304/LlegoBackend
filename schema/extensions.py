"""GraphQL schema extensions."""
import asyncio
import traceback
from strawberry.extensions import SchemaExtension

from services.error_analysis_service import error_analysis_service, sanitize_sensitive_data
from domain.error_logs import ErrorSource


class UserIdExtension(SchemaExtension):
    """Attach user_id to GraphQL response extensions when present."""

    def on_request_end(self) -> None:
        context = self.execution_context.context
        if not isinstance(context, dict):
            return

        user_id = context.get("user_id")
        if not user_id or not self.execution_context.result:
            return

        result = self.execution_context.result
        if result.extensions is None:
            result.extensions = {}
        result.extensions["user_id"] = user_id


class ErrorLoggingExtension(SchemaExtension):
    """Log GraphQL errors to MongoDB and trigger Gemini analysis."""

    def on_request_end(self) -> None:
        result = self.execution_context.result
        if not result or not result.errors:
            return

        context = self.execution_context.context
        request = context.get("request") if isinstance(context, dict) else None

        for error in result.errors:
            # Skip client errors (validation, etc)
            if not error.original_error:
                continue

            # Log in background
            asyncio.create_task(self._log_error(error, request, context))

    async def _log_error(self, error, request, context) -> None:
        """Log error to database and trigger analysis."""
        from repositories.error_log_repository import error_log_repo

        try:
            original = error.original_error
            stack_trace = "".join(traceback.format_exception(
                type(original), original, original.__traceback__
            ))

            # Extract request info
            client_ip = "unknown"
            user_agent = None
            endpoint = "/graphql"

            if request:
                # Get client IP
                forwarded = request.headers.get("x-forwarded-for")
                if forwarded:
                    client_ip = forwarded.split(",")[0].strip()
                elif request.client:
                    client_ip = request.client.host

                user_agent = request.headers.get("user-agent")

            user_id = context.get("user_id") if isinstance(context, dict) else None

            error_data = {
                "error_type": type(original).__name__,
                "error_message": str(original),
                "stack_trace": sanitize_sensitive_data(stack_trace),
                "endpoint": endpoint,
                "http_method": "POST",
                "client_ip": client_ip,
                "user_agent": user_agent,
                "user_id": user_id,
                "source": ErrorSource.BACKEND.value
            }

            error_log = await error_log_repo.create(error_data)

            # Trigger background analysis
            asyncio.create_task(
                error_analysis_service.analyze_and_update(error_log.id, error_data)
            )

        except Exception as e:
            print(f"Failed to log GraphQL error: {e}")
