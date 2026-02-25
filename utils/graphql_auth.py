"""GraphQL auth helpers."""
from typing import Optional

from strawberry.types import Info

from utils.auth import decode_access_token


def apply_optional_jwt(jwt: Optional[str], info: Info) -> Optional[str]:
    """Validate optional JWT and store user_id in context."""
    if not jwt:
        return None

    payload = decode_access_token(jwt)
    if not payload or "user_id" not in payload:
        raise Exception("Invalid JWT")

    user_id = payload.get("user_id")
    if isinstance(info.context, dict):
        info.context["user_id"] = user_id
        info.context["user_role"] = payload.get("role")
    else:
        info.context.user_id = user_id
        info.context.user_role = payload.get("role")
    return user_id


def require_auth(jwt: Optional[str], info: Info) -> str:
    """Require valid JWT authentication. Raises if not authenticated."""
    user_id = apply_optional_jwt(jwt, info)
    if not user_id:
        raise Exception("Autenticación requerida")
    return user_id


def require_role(jwt: Optional[str], info: Info, allowed_roles: list[str]) -> str:
    """
    Require valid JWT with specific role(s).
    
    Args:
        jwt: JWT token
        info: Strawberry Info context
        allowed_roles: List of allowed roles (e.g., ["admin", "manager"])
    
    Returns:
        user_id if authorized
        
    Raises:
        Exception if not authenticated or role not allowed
    """
    user_id = require_auth(jwt, info)
    user_role = info.context.get("user_role")
    
    if user_role not in allowed_roles:
        raise Exception(f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}")
    
    return user_id
