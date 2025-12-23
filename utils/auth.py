"""Authentication utilities for password hashing and JWT tokens."""
from datetime import datetime, timedelta
from hashlib import sha256
from typing import List, Optional, Union

import bcrypt
from jose import JWTError, jwt

# JWT configuration
SECRET_KEY = "llego-secret-key-change-in-production"  # TODO: Move to environment variables
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Social Login Imports
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as grequests
    import requests
    import jwt
    from fastapi import HTTPException
    from core.config import settings
except ImportError:
    # Fallback or allow validation to fail if libs missing
    pass

# Apple Configuration
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISS = "https://appleid.apple.com"
_apple_keys_cache = []

# bcrypt input limit
MAX_BCRYPT_BYTES = 72


def _get_apple_audiences() -> Union[str, List[str]]:
    """Return Apple audiences, supporting comma-separated env values."""
    raw_audience = settings.apple_client_id
    if not isinstance(raw_audience, str):
        return raw_audience

    parts = [part.strip() for part in raw_audience.split(",") if part.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else raw_audience
    return parts


def _prepare_password(password: str) -> bytes:
    """
    Prepare password for bcrypt hashing, ensuring it fits within the 72-byte limit.

    If the password exceeds 72 bytes, SHA-256 is applied first to create a
    fixed-length 64-character hex digest that safely fits within bcrypt's limit.
    This allows passwords of any length to be securely hashed.

    Args:
        password: The plain text password to prepare.

    Returns:
        bytes: Password bytes ready for bcrypt hashing (guaranteed ≤ 72 bytes).
    """
    if not isinstance(password, str):
        raise ValueError("password must be a string")

    raw_bytes = password.encode("utf-8")
    if len(raw_bytes) <= MAX_BCRYPT_BYTES:
        return raw_bytes

    digest = sha256(raw_bytes).hexdigest()
    return digest.encode("ascii")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with automatic SHA-256 preprocessing for long passwords.

    Returns:
        str: The bcrypt hash (60 characters starting with $2b$).
    """
    prepared = _prepare_password(password)
    hashed = bcrypt.hashpw(prepared, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash with legacy fallback support.
    """
    if plain_password is None or hashed_password is None:
        return False

    try:
        hashed_bytes = hashed_password.encode("utf-8")
    except AttributeError:
        return False

    try:
        prepared = _prepare_password(plain_password)
        if bcrypt.checkpw(prepared, hashed_bytes):
            return True
    except Exception:
        # Fall back to legacy handling below
        pass

    try:
        legacy_candidate = plain_password.encode("utf-8")[:MAX_BCRYPT_BYTES]
        return bcrypt.checkpw(legacy_candidate, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def verify_google(id_token_str: str, nonce: str = None) -> dict:
    """Verify Google ID token."""
    try:
        claims = id_token.verify_oauth2_token(
            id_token_str,
            grequests.Request(),
            audience=settings.google_client_id
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")

    if nonce and claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="Invalid nonce")
        
    return {
        "sub": claims["sub"],
        "email": claims["email"],
        "name": claims.get("name", claims["email"].split("@")[0]),
        "picture": claims.get("picture")
    }


def get_apple_keys():
    """Fetch Apple public keys with caching."""
    global _apple_keys_cache
    if not _apple_keys_cache:
         # simple caching
        try:
            response = requests.get(APPLE_KEYS_URL, timeout=5)
            if response.status_code == 200:
                _apple_keys_cache = response.json().get("keys", [])
        except Exception:
            pass
    return _apple_keys_cache


def verify_apple(identity_token: str, nonce: str = None) -> dict:
    """Verify Apple Identity Token."""
    keys = get_apple_keys()
    try:
        header = jwt.get_unverified_header(identity_token)
        key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
        
        if not key:
             # Force refresh keys
            global _apple_keys_cache
            _apple_keys_cache = []
            keys = get_apple_keys()
            key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
            if not key:
                raise Exception("Apple key not found")
        
        rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
        claims = jwt.decode(
            identity_token,
            rsa_key,
            algorithms=[header["alg"]],
            audience=_get_apple_audiences(),
            issuer=APPLE_ISS
        )
    except Exception as e:
         raise HTTPException(status_code=401, detail=f"Invalid Apple token: {str(e)}")

    if nonce and claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="Invalid nonce")
        
    return {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "is_private_email": claims.get("is_private_email")
    }
