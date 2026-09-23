"""Modo sandbox E2E: probar flujos completos contra el backend DESPLEGADO sin
tocar datos de produccion.

Una peticion HTTP que trae el header `X-E2E-Key` con la clave correcta
(`E2E_SANDBOX_KEY`) se ejecuta con el mismo codigo desplegado, pero:

- Lee y escribe en otra base de datos (`E2E_DATABASE`, por defecto
  `<MONGODB_DATABASE>_e2e`). Ver `clients.mongodb_client.get_database`.
- Firma y valida JWT con un secreto derivado: un token del sandbox no sirve en
  produccion y uno de produccion no sirve en el sandbox. Ver `utils.auth`.
- No usa la cache de Redis (claves compartidas con produccion) ni registra
  errores/analisis con IA (los tests de fallo generan errores a proposito).

Garantias de seguridad:
- Si `E2E_SANDBOX_KEY` esta vacia el modo no existe: cualquier peticion con el
  header responde 403 en vez de caer silenciosamente en produccion.
- Clave incorrecta -> 403. Nunca se "degrada" a produccion.
- La base del sandbox nunca puede ser la de produccion (se valida al activar).
- Los workers de fondo (timeouts, etc.) corren fuera de cualquier peticion, asi
  que siempre operan sobre produccion y nunca tocan pedidos del sandbox.
"""

import contextvars
import hashlib
import hmac
from typing import Optional

from core.config import settings

SANDBOX_HEADER = "X-E2E-Key"
SANDBOX_RESPONSE_HEADER = "X-E2E-Sandbox"

_sandbox_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "llego_e2e_sandbox_active", default=False
)


class SandboxConfigError(RuntimeError):
    """Configuracion del sandbox insegura (p. ej. apunta a la BD de produccion)."""


def sandbox_enabled() -> bool:
    return bool(settings.e2e_sandbox_key)


def is_sandbox() -> bool:
    return _sandbox_active.get()


def key_matches(provided: Optional[str]) -> bool:
    if not sandbox_enabled() or not provided:
        return False
    return hmac.compare_digest(provided.encode(), settings.e2e_sandbox_key.encode())


def sandbox_database_name() -> str:
    name = settings.e2e_database or f"{settings.mongodb_database}_e2e"
    if name == settings.mongodb_database:
        raise SandboxConfigError(
            "E2E_DATABASE no puede ser la misma base de datos de produccion"
        )
    return name


def activate() -> contextvars.Token:
    # Valida la configuracion ANTES de activar: si fuera insegura, la peticion
    # falla en vez de ejecutarse contra produccion.
    sandbox_database_name()
    return _sandbox_active.set(True)


def deactivate(token: contextvars.Token) -> None:
    _sandbox_active.reset(token)


def sandbox_jwt_secret(base_secret: str) -> str:
    """Secreto JWT del sandbox, derivado del de produccion y de la clave E2E."""
    return hmac.new(
        base_secret.encode(),
        b"llego-e2e-sandbox:" + settings.e2e_sandbox_key.encode(),
        hashlib.sha256,
    ).hexdigest()
