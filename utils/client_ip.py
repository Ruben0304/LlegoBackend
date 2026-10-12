"""IP del cliente para el rate limit y los logs, sin fiarse de cabeceras falsificables.

Antes se usaba el primer valor de `X-Forwarded-For`, que lo escribe el propio
cliente: rotándolo, cada petición caía en un cubo de rate limit nuevo y el
límite por IP no frenaba a nadie. Ahora el orden es:

1. **Petición de la web (LlegoWeb) con el secreto compartido.** La web llama al
   backend desde su servidor (proxy `/api/graphql`, login social), así que el
   backend ve la IP del servidor de la web, no la del navegador. La web reenvía
   la IP real en `X-Llego-Client-IP` (y en `X-Forwarded-For`) junto con
   `X-Llego-Proxy-Secret`; solo si el secreto coincide con `WEB_PROXY_SECRET`
   (comparación en tiempo constante) se usa esa IP. Se lee primero la cabecera
   propia porque el edge de Railway reescribe `X-Forwarded-For` cuando la web
   entra por el dominio público; si la web usa la red privada
   (`*.railway.internal`) las dos llegan intactas.
2. **`X-Real-IP`**: la pone el edge de Railway con la IP remota del cliente en
   cada petición HTTP (documentado en Railway, "Specs & Limits" de Public
   Networking) y la sobrescribe si el cliente la manda. Por la red privada no
   pasa por el edge, pero ahí solo llegan servicios del propio proyecto.
3. **`request.client.host`**: conexión TCP directa (local, tests).

Sin `WEB_PROXY_SECRET` configurado (por defecto) el paso 1 no existe: nunca se
acepta una IP reenviada, aunque alguien mande las cabeceras.
"""

import hmac
import ipaddress
from typing import Any, Optional

from core.config import settings

# Cabeceras que manda la web desde su servidor (src/lib/shared/backend-proxy.ts).
WEB_PROXY_SECRET_HEADER = "x-llego-proxy-secret"
WEB_PROXY_CLIENT_IP_HEADER = "x-llego-client-ip"
FORWARDED_FOR_HEADER = "x-forwarded-for"
# La pone el edge de Railway con la IP del cliente.
REAL_IP_HEADER = "x-real-ip"

UNKNOWN_IP = "unknown"


def _parse_ip(value: Optional[str]) -> Optional[str]:
    """IP normalizada, o None si el valor no es una IP (basura, vacío, puerto)."""
    if not value or not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def is_trusted_web_proxy(request: Any) -> bool:
    """True si la petición trae el secreto compartido con la web.

    Sin `WEB_PROXY_SECRET` configurado siempre es False.
    """
    secret = settings.web_proxy_secret
    if not secret or request is None:
        return False
    provided = request.headers.get(WEB_PROXY_SECRET_HEADER)
    if not provided or not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided.encode(), secret.encode())


def _ip_forwarded_by_web(request: Any) -> Optional[str]:
    """IP del navegador que reenvía la web, solo con el secreto válido."""
    if not is_trusted_web_proxy(request):
        return None
    forwarded_ip = _parse_ip(request.headers.get(WEB_PROXY_CLIENT_IP_HEADER))
    if forwarded_ip:
        return forwarded_ip
    # Por la red privada de Railway X-Forwarded-For llega tal como lo puso la web.
    forwarded_for = request.headers.get(FORWARDED_FOR_HEADER)
    if not isinstance(forwarded_for, str):
        return None
    return _parse_ip(forwarded_for.split(",")[0])


def get_client_ip(request: Any) -> str:
    """IP del cliente de una petición HTTP o WebSocket de Starlette."""
    if request is None:
        return UNKNOWN_IP

    ip = _ip_forwarded_by_web(request) or _parse_ip(request.headers.get(REAL_IP_HEADER))
    if ip:
        return ip

    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return host or UNKNOWN_IP
