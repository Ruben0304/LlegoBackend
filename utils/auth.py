"""Authentication utilities for password hashing and JWT tokens."""
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Optional

import bcrypt
from jose import JWTError, jwt

# JWT configuration
SECRET_KEY = "llego-secret-key-change-in-production"  # TODO: Move to environment variables
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# bcrypt input limit
MAX_BCRYPT_BYTES = 72


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
    except JWTError:
        return None
