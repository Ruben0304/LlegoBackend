"""GraphQL schema extensions."""
import asyncio
import time
import traceback
from datetime import datetime
from strawberry.extensions import SchemaExtension

from services.error_analysis_service import error_analysis_service, sanitize_sensitive_data
from domain.error_logs import ErrorSource


class UserIdExtension(SchemaExtension):
    """Attach user_id to GraphQL response extensions when present."""

    def on_request_end(self) -> None:
        context = self.execution_context.context
        user_id = context.get("user_id") if isinstance(context, dict) else getattr(context, "user_id", None)
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
        request = context.get("request") if isinstance(context, dict) else getattr(context, "request", None)

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

            user_id = context.get("user_id") if isinstance(context, dict) else getattr(context, "user_id", None)

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


# Throttle state for LastSeenExtension: {user_id: monotonic timestamp of last write}.
# Per-process, so with N workers the worst case is N writes per user per window —
# which is fine, and far better than one write per request.
_LAST_SEEN_WRITES: dict[str, float] = {}
_LAST_SEEN_THROTTLE_SECONDS = 3600.0
# Hard cap so the dict can't grow unbounded on a long-lived process.
_LAST_SEEN_MAX_TRACKED = 50_000


class LastSeenExtension(SchemaExtension):
    """Record that an authenticated user was active, at most once per hour.

    This is the *only* activity signal the backend has: `login` doesn't touch
    the user document, JWTs are stateless and last 30 days, and there is no
    session or analytics collection. Without this, "active users" can't be
    measured at all (see admin_user_metrics in schema/users/queries.py).

    Known gap: REST endpoints authenticate via utils/auth.get_current_user_id_from_header
    and never reach a GraphQL extension, so their traffic doesn't count as
    activity. The apps are overwhelmingly GraphQL, so this is acceptable.
    """

    def on_request_end(self) -> None:
        context = self.execution_context.context
        user_id = (
            context.get("user_id")
            if isinstance(context, dict)
            else getattr(context, "user_id", None)
        )
        if not user_id:
            return

        user_id = str(user_id)
        now = time.monotonic()
        last_write = _LAST_SEEN_WRITES.get(user_id)
        if last_write is not None and (now - last_write) < _LAST_SEEN_THROTTLE_SECONDS:
            return

        # Mark before writing so concurrent requests in this process don't pile up.
        if len(_LAST_SEEN_WRITES) >= _LAST_SEEN_MAX_TRACKED:
            _LAST_SEEN_WRITES.clear()
        _LAST_SEEN_WRITES[user_id] = now

        # Fire-and-forget: never add latency to the response for a metric.
        try:
            asyncio.create_task(self._touch_last_seen(user_id))
        except RuntimeError:
            # No running loop (e.g. sync test execution) — drop it silently.
            _LAST_SEEN_WRITES.pop(user_id, None)

    @staticmethod
    async def _touch_last_seen(user_id: str) -> None:
        from bson import ObjectId

        from clients import get_database

        try:
            await get_database()["users"].update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"lastSeenAt": datetime.utcnow()}},
            )
        except Exception as e:
            # Never let a metrics write surface to the client.
            print(f"Failed to update lastSeenAt for {user_id}: {e}")
