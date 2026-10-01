"""Apple Sign In Web Auth endpoints for Android/Kotlin clients."""

import json
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import settings
from repositories import auth_repo
from services.apple_web_auth import (
    exchange_code_for_tokens,
    get_authorization_url,
    verify_id_token,
)
from utils.auth import create_access_token, get_apple_private_email

router = APIRouter(prefix="/apple", tags=["Apple Auth (Android)"])

# Lista blanca de destinos del callback. /apple/callback redirige con
# ?token=JWT, asi que aceptar un destino arbitrario (p. ej.
# redirect_scheme=https://atacante/x?) le entregaria la sesion a quien lo pida.
# Solo valen los esquemas de las apps que usan este flujo y las URL web exactas
# de WEB_AUTH_CALLBACK_URLS.
DEEP_LINK_SCHEMES = {
    "llego": "llego://auth/callback",  # LlegoApk
    "llegobusiness": "llegobusiness://auth/callback",  # LlegoBussisnes Android
}
DEFAULT_DEEP_LINK = DEEP_LINK_SCHEMES["llego"]

# In-memory state storage (use Redis in production for multi-instance)
_pending_states: dict[str, dict] = {}


class AppleAuthStartResponse(BaseModel):
    """Response for starting Apple auth flow."""

    auth_url: str
    state: str


def resolve_redirect_uri(redirect_scheme: str) -> Optional[str]:
    """Destino permitido para `redirect_scheme`, o None si no esta en la lista blanca.

    Acepta el nombre de un esquema de app (`llego`, `llegobusiness`) o una URL
    de callback web que coincida exactamente (salvo la barra final) con una de
    WEB_AUTH_CALLBACK_URLS.
    """
    candidate = (redirect_scheme or "").strip()
    if candidate in DEEP_LINK_SCHEMES:
        return DEEP_LINK_SCHEMES[candidate]
    for allowed_url in settings.web_auth_callback_url_list:
        if candidate.rstrip("/") == allowed_url.rstrip("/"):
            return allowed_url
    return None


@router.get("/start", response_model=AppleAuthStartResponse)
async def start_apple_auth(redirect_scheme: str = "llego"):
    """
    Start Apple Sign In flow (Android apps y web).

    Args:
        redirect_scheme: esquema de la app ("llego" o "llegobusiness") o una URL
            de callback web incluida en WEB_AUTH_CALLBACK_URLS. Cualquier otro
            valor devuelve 400 y no crea state.

    Returns URL to open in Custom Tab/WebView.
    The state should be stored client-side to verify callback.
    """
    redirect_uri = resolve_redirect_uri(redirect_scheme)
    if redirect_uri is None:
        raise HTTPException(
            status_code=400, detail="redirect_scheme no permitido"
        )

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)

    # Store state for verification with the redirect URI
    _pending_states[state] = {"nonce": nonce, "redirect_uri": redirect_uri}

    auth_url = get_authorization_url(state=state, nonce=nonce)

    return AppleAuthStartResponse(auth_url=auth_url, state=state)


@router.post("/callback")
async def apple_callback(request: Request):
    """
    Handle Apple Sign In callback (POST from Apple).

    Apple sends:
    - code: Authorization code to exchange for tokens
    - id_token: JWT with user info
    - state: Our state for CSRF verification
    - user: JSON string with name/email (ONLY on first authorization)

    Redirects to Android app via deep link with our JWT token.
    """
    import logging

    logger = logging.getLogger(__name__)

    form_data = await request.form()

    logger.info("=== APPLE CALLBACK RECEIVED ===")
    logger.info(f"Form data keys: {list(form_data.keys())}")

    code = form_data.get("code")
    id_token_str = form_data.get("id_token")
    state = form_data.get("state")
    user_json = form_data.get("user")  # Only first time
    error = form_data.get("error")

    logger.info(f"code: {code[:20] if code else None}...")
    logger.info(f"id_token: {id_token_str[:50] if id_token_str else None}...")
    logger.info(f"state: {state}")
    logger.info(f"user_json: {user_json}")
    logger.info(f"error: {error}")
    logger.info(f"Pending states: {list(_pending_states.keys())}")

    # Get the redirect URI for this state (or use default)
    stored_state = _pending_states.get(state, {})
    redirect_uri = stored_state.get("redirect_uri", DEFAULT_DEEP_LINK)
    logger.info(f"Using redirect URI: {redirect_uri}")

    # Handle Apple errors
    if error:
        logger.error(f"Apple returned error: {error}")
        return RedirectResponse(url=f"{redirect_uri}?error={error}", status_code=303)

    # Verify state
    if not state or state not in _pending_states:
        logger.error(f"Invalid state: {state}, pending: {list(_pending_states.keys())}")
        return RedirectResponse(
            url=f"{redirect_uri}?error=invalid_state", status_code=303
        )

    # Clean up state
    _pending_states.pop(state, {})
    logger.info(
        f"State verified and removed. Stored nonce: {stored_state.get('nonce')}"
    )

    try:
        # Verify the id_token from Apple
        logger.info("Verifying id_token...")
        token_info = verify_id_token(id_token_str)
        logger.info(
            f"Token verified. sub: {token_info.get('sub')}, email: {token_info.get('email')}"
        )

        # Parse user info if provided (first authorization only)
        user_name = None
        if user_json:
            try:
                user_data = json.loads(user_json)
                name_data = user_data.get("name", {})
                first_name = name_data.get("firstName", "")
                last_name = name_data.get("lastName", "")
                user_name = f"{first_name} {last_name}".strip() or None
                logger.info(f"Parsed user name: {user_name}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse user_json: {e}")

        # Create or update user in database
        logger.info("Upserting user in database...")
        user = await auth_repo.upsert_social_user(
            email=token_info["email"],
            provider="apple",
            provider_user_id=token_info["sub"],
            name=user_name,
            apple_private_email=get_apple_private_email(
                token_info.get("email"), token_info.get("is_private_email")
            ),
        )
        logger.info(f"User upserted: id={user.id}, email={user.email}")

        # Generate our JWT token
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id, "role": user.role}
        )
        logger.info(f"JWT created, length: {len(access_token)}")

        # Redirect to Android app with token
        final_redirect = f"{redirect_uri}?token={access_token}"
        logger.info(f"Redirecting to: {final_redirect[:100]}...")
        logger.info("=== APPLE CALLBACK SUCCESS ===")

        return RedirectResponse(url=final_redirect, status_code=303)

    except Exception as e:
        logger.exception(f"Apple callback failed: {e}")
        error_msg = str(e).replace(" ", "_")[:100]  # URL-safe error
        return RedirectResponse(
            url=f"{redirect_uri}?error=auth_failed&message={error_msg}", status_code=303
        )


@router.get("/callback")
async def apple_callback_get(request: Request):
    """
    Handle GET callback (for error cases or manual testing).
    Apple normally uses POST, but errors might come as GET.
    """
    error = request.query_params.get("error")
    if error:
        # Antes usaba ANDROID_DEEP_LINK, que no existe: NameError y 500.
        return RedirectResponse(
            url=f"{DEFAULT_DEEP_LINK}?error={error}", status_code=303
        )

    return {"message": "Use POST for Apple callback"}
