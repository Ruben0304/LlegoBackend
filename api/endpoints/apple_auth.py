"""Apple Sign In Web Auth endpoints for Android/Kotlin clients."""
import secrets
import json
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from services.apple_web_auth import (
    get_authorization_url,
    exchange_code_for_tokens,
    verify_id_token,
)
from repositories import auth_repo
from utils.auth import create_access_token

router = APIRouter(prefix="/apple", tags=["Apple Auth (Android)"])

# Deep link scheme for Android app
ANDROID_DEEP_LINK = "llegobusiness://auth/callback"

# In-memory state storage (use Redis in production for multi-instance)
_pending_states: dict[str, dict] = {}


class AppleAuthStartResponse(BaseModel):
    """Response for starting Apple auth flow."""
    auth_url: str
    state: str


@router.get("/start", response_model=AppleAuthStartResponse)
async def start_apple_auth():
    """
    Start Apple Sign In flow for Android.
    
    Returns URL to open in Custom Tab/WebView.
    The state should be stored client-side to verify callback.
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    
    # Store state for verification (expires in 10 minutes)
    _pending_states[state] = {"nonce": nonce}
    
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
    form_data = await request.form()
    
    code = form_data.get("code")
    id_token_str = form_data.get("id_token")
    state = form_data.get("state")
    user_json = form_data.get("user")  # Only first time
    error = form_data.get("error")
    
    # Handle Apple errors
    if error:
        return RedirectResponse(
            url=f"{ANDROID_DEEP_LINK}?error={error}",
            status_code=303
        )
    
    # Verify state
    if not state or state not in _pending_states:
        return RedirectResponse(
            url=f"{ANDROID_DEEP_LINK}?error=invalid_state",
            status_code=303
        )
    
    # Clean up state
    stored_state = _pending_states.pop(state, {})
    
    try:
        # Verify the id_token from Apple
        token_info = verify_id_token(id_token_str)
        
        # Parse user info if provided (first authorization only)
        user_name = None
        if user_json:
            try:
                user_data = json.loads(user_json)
                name_data = user_data.get("name", {})
                first_name = name_data.get("firstName", "")
                last_name = name_data.get("lastName", "")
                user_name = f"{first_name} {last_name}".strip() or None
            except json.JSONDecodeError:
                pass
        
        # Create or update user in database
        user = await auth_repo.upsert_social_user(
            email=token_info["email"],
            provider="apple",
            provider_user_id=token_info["sub"],
            name=user_name,
            apple_private_email=token_info.get("is_private_email", False)
        )
        
        # Generate our JWT token
        access_token = create_access_token(data={
            "sub": user.email,
            "user_id": user.id,
            "role": user.role
        })
        
        # Redirect to Android app with token
        return RedirectResponse(
            url=f"{ANDROID_DEEP_LINK}?token={access_token}",
            status_code=303
        )
        
    except Exception as e:
        return RedirectResponse(
            url=f"{ANDROID_DEEP_LINK}?error=auth_failed&message={str(e)}",
            status_code=303
        )


@router.get("/callback")
async def apple_callback_get(request: Request):
    """
    Handle GET callback (for error cases or manual testing).
    Apple normally uses POST, but errors might come as GET.
    """
    error = request.query_params.get("error")
    if error:
        return RedirectResponse(
            url=f"{ANDROID_DEEP_LINK}?error={error}",
            status_code=303
        )
    
    return {"message": "Use POST for Apple callback"}
