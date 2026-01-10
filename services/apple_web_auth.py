"""Apple Sign In Web Auth Service for Android/Kotlin clients."""
import time
import jwt
import requests
from typing import Optional
from urllib.parse import urlencode

from core.config import settings

# Apple endpoints
APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

# Cache for Apple public keys
_apple_keys_cache = []


def _get_private_key() -> str:
    """
    Get Apple private key from environment variable.
    The key should be stored as a single-line string with \\n for newlines.
    """
    key = settings.apple_private_key
    if not key:
        raise ValueError("APPLE_PRIVATE_KEY not configured")
    # Handle escaped newlines from env var
    return key.replace("\\n", "\n")


def generate_client_secret() -> str:
    """
    Generate Apple client_secret JWT.
    Required for exchanging authorization code for tokens.
    Valid for 6 months max, we generate for 5 minutes.
    """
    now = int(time.time())
    payload = {
        "iss": settings.apple_team_id,
        "iat": now,
        "exp": now + 300,  # 5 minutes
        "aud": "https://appleid.apple.com",
        "sub": settings.apple_web_service_id,
    }
    
    private_key = _get_private_key()
    
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": settings.apple_key_id}
    )


def get_authorization_url(state: str, nonce: Optional[str] = None) -> str:
    """
    Generate Apple authorization URL for web flow.
    
    Args:
        state: Random state for CSRF protection (store in session/cache)
        nonce: Optional nonce for additional security
    
    Returns:
        URL to redirect user to Apple Sign In
    """
    params = {
        "client_id": settings.apple_web_service_id,
        "redirect_uri": settings.apple_web_redirect_uri,
        "response_type": "code id_token",
        "response_mode": "form_post",
        "scope": "name email",
        "state": state,
    }
    
    if nonce:
        params["nonce"] = nonce
    
    return f"{APPLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange authorization code for Apple tokens.
    
    Args:
        code: Authorization code from Apple callback
    
    Returns:
        Dict with id_token, access_token, refresh_token
    """
    client_secret = generate_client_secret()
    
    data = {
        "client_id": settings.apple_web_service_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.apple_web_redirect_uri,
    }
    
    response = requests.post(APPLE_TOKEN_URL, data=data, timeout=10)
    
    if response.status_code != 200:
        raise ValueError(f"Apple token exchange failed: {response.text}")
    
    return response.json()


def get_apple_public_keys() -> list:
    """Fetch Apple public keys with caching."""
    global _apple_keys_cache
    if not _apple_keys_cache:
        response = requests.get(APPLE_KEYS_URL, timeout=5)
        if response.status_code == 200:
            _apple_keys_cache = response.json().get("keys", [])
    return _apple_keys_cache


def verify_id_token(id_token: str) -> dict:
    """
    Verify and decode Apple ID token.
    
    Returns:
        Dict with sub (Apple user ID), email, email_verified, is_private_email
    """
    keys = get_apple_public_keys()
    header = jwt.get_unverified_header(id_token)
    
    key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    
    if not key:
        # Force refresh keys
        global _apple_keys_cache
        _apple_keys_cache = []
        keys = get_apple_public_keys()
        key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        if not key:
            raise ValueError("Apple public key not found")
    
    rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
    
    # Apple web service ID is the audience for web flow
    claims = jwt.decode(
        id_token,
        rsa_key,
        algorithms=[header["alg"]],
        audience=settings.apple_web_service_id,
        issuer="https://appleid.apple.com"
    )
    
    return {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "email_verified": claims.get("email_verified"),
        "is_private_email": claims.get("is_private_email", False),
    }
