"""GraphQL auth helpers."""
from typing import Optional

from strawberry.types import Info

from utils.auth import decode_access_token


def apply_optional_jwt(jwt: Optional[str], info: Info) -> Optional[str]:
    """Validate optional JWT and store user_id in context."""
    if not jwt:
        return None

    payload = decode_access_token(jwt)
    if not payload:
        raise Exception("Invalid JWT")

    user_id = payload.get("user_id")
    if isinstance(info.context, dict):
        info.context["user_id"] = user_id
    return user_id
