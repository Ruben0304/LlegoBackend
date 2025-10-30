"""Authentication utilities for password hashing and JWT tokens."""
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from hashlib import sha256

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        password: The plain text password to prepare

    Returns:
        bytes: Password bytes ready for bcrypt hashing (guaranteed ≤ 72 bytes)
    """
    if password is None:
        raise ValueError("password must be a string")

    raw_bytes = password.encode("utf-8")

    if len(raw_bytes) <= MAX_BCRYPT_BYTES:
        # Password fits within bcrypt's limit, use directly
        return raw_bytes

    # Password exceeds 72 bytes: apply SHA-256 first
    # SHA-256 produces a 64-character hex digest (64 ASCII bytes), which always fits
    digest = sha256(raw_bytes).hexdigest()
    return digest.encode("ascii")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with automatic SHA-256 preprocessing for long passwords.

    This function safely handles passwords of any length by:
    1. Using the password directly if ≤ 72 bytes
    2. Applying SHA-256 first if > 72 bytes, then hashing the result

    Args:
        password: The plain text password to hash

    Returns:
        str: The bcrypt hash (60 characters starting with $2b$)
    """
    prepared = _prepare_password(password)
    return pwd_context.hash(prepared.decode("utf-8") if isinstance(prepared, bytes) else prepared)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.

    This function includes fallback logic for backward compatibility:
    1. First tries with preprocessing (_prepare_password)
    2. Falls back to direct comparison (for old passwords stored with truncation)

    Args:
        plain_password: The plain text password to verify
        hashed_password: The bcrypt hash to verify against

    Returns:
        bool: True if password matches, False otherwise
    """
    if plain_password is None:
        return False

    try:
        # Try with preprocessing (new method)
        prepared = _prepare_password(plain_password)
        return pwd_context.verify(prepared.decode("utf-8") if isinstance(prepared, bytes) else prepared, hashed_password)
    except Exception:
        try:
            # Fallback for old passwords that were truncated
            pw_bytes = plain_password.encode("utf-8")[:72]
            safe_password = pw_bytes.decode("utf-8", errors="ignore")
            return pwd_context.verify(safe_password, hashed_password)
        except Exception:
            # Hash is invalid or corrupted
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
