"""GraphQL schema extensions."""
import asyncio
import time
import traceback
from datetime import datetime
from graphql import GraphQLError
from strawberry.extensions import MaskErrors, SchemaExtension

from core.sandbox import is_sandbox
from services.courier_access import COURIER_NOT_APPROVED
from services.error_analysis_service import error_analysis_service, sanitize_sensitive_data
from domain.error_logs import ErrorSource
from utils.client_ip import get_client_ip

# Errores esperados del flujo normal, no fallos del backend: no se registran en
# error_logs ni se mandan a analizar (cada análisis acaba en un push a los
# admins). COURIER_NOT_APPROVED lo recibe en cada sondeo la app de mensajeros de
# un usuario sin aprobar (services/courier_access.py).
EXPECTED_ERROR_PREFIXES = (COURIER_NOT_APPROVED,)


# ---------------------------------------------------------------------------
# Enmascarar errores inesperados
#
# Los resolvers devuelven al cliente el texto de la excepción. Para los mensajes de
# negocio ("No autorizado", "Ya tienes un pedido en curso"...) es lo que se quiere,
# pero un fallo interno (AttributeError, KeyError, un error de Mongo o de red...)
# puede llevar nombres de campos, rutas o datos internos. Esos se sustituyen por un
# mensaje genérico; el resto llega igual que antes.
#
# A diferencia de strawberry.extensions.MaskErrors, se conserva `original_error` en
# el error enmascarado: ErrorLoggingExtension lo usa (en on_request_end, que corre
# después) para registrar el fallo real en error_logs.
# ---------------------------------------------------------------------------

UNEXPECTED_ERROR_MESSAGE = "Error interno. Inténtalo de nuevo en unos minutos."


def _unexpected_error_types() -> tuple:
    types = [
        AttributeError, KeyError, IndexError, TypeError, NameError,
        ZeroDivisionError, AssertionError, RecursionError, UnicodeError, OSError,
    ]
    try:  # errores de MongoDB/BSON
        from pymongo.errors import PyMongoError
        from bson.errors import BSONError
        types += [PyMongoError, BSONError]
    except ImportError:  # pragma: no cover
        pass
    try:  # validación de modelos (es subclase de ValueError: hay que nombrarla)
        from pydantic import ValidationError
        types.append(ValidationError)
    except ImportError:  # pragma: no cover
        pass
    try:  # llamadas HTTP salientes
        import httpx
        types.append(httpx.HTTPError)
    except ImportError:  # pragma: no cover
        pass
    import json
    types.append(json.JSONDecodeError)
    return tuple(types)


UNEXPECTED_ERROR_TYPES = _unexpected_error_types()


def _leaks_unexpected_error(error: BaseException) -> bool:
    """Un `Exception("Error al crear: {e}")` que envuelve un fallo interno y repite su texto."""
    message = str(error)
    seen = set()
    inner = error.__cause__ or error.__context__
    while inner is not None and id(inner) not in seen:
        seen.add(id(inner))
        if isinstance(inner, UNEXPECTED_ERROR_TYPES):
            inner_text = str(inner)
            if inner_text and inner_text in message:
                return True
        inner = inner.__cause__ or inner.__context__
    return False


def should_mask_error(error: GraphQLError) -> bool:
    """True si el error es un fallo interno y su texto no debe llegar al cliente.

    Los errores sin original_error (validación de la query, sintaxis) no se tocan.
    """
    original = error.original_error
    if original is None:
        return False
    if isinstance(original, UNEXPECTED_ERROR_TYPES):
        return True
    return _leaks_unexpected_error(original)


class MaskUnexpectedErrors(MaskErrors):
    """MaskErrors que conserva el error original para el log (ver arriba)."""

    def __init__(self, *, execution_context=None) -> None:
        # Strawberry instancia las extensiones registradas como clase en cada petición
        # (una por operación, sin estado compartido entre peticiones concurrentes).
        super().__init__(should_mask_error=should_mask_error, error_message=UNEXPECTED_ERROR_MESSAGE)
        if execution_context is not None:
            self.execution_context = execution_context

    def anonymise_error(self, error: GraphQLError) -> GraphQLError:
        return GraphQLError(
            message=self.error_message,
            nodes=error.nodes,
            source=error.source,
            positions=error.positions,
            path=error.path,
            original_error=error.original_error,
            extensions={},
        )


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

        # Los tests E2E provocan errores a proposito (permisos, estados
        # invalidos...): ni se registran ni se mandan a analizar con IA.
        if is_sandbox():
            return

        context = self.execution_context.context
        request = context.get("request") if isinstance(context, dict) else getattr(context, "request", None)

        for error in result.errors:
            # Skip client errors (validation, etc)
            if not error.original_error:
                continue

            if str(error.original_error).startswith(EXPECTED_ERROR_PREFIXES):
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
                # Misma regla que el rate limit: no el X-Forwarded-For del cliente.
                client_ip = get_client_ip(request)

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
