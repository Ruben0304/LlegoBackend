"""Authentication utilities for password hashing and JWT tokens."""
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = "llego-secret-key-change-in-production"  # TODO: Move to environment variables
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    # bcrypt has a 72-byte input limit. Truncate to 72 bytes to avoid ValueError
    # while preserving valid UTF-8 characters.
    if password is None:
        raise ValueError("password must be a string")

    pw_bytes = password.encode("utf-8")[:72]
    safe_password = pw_bytes.decode("utf-8", errors="ignore")
    return pwd_context.hash(safe_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # When we hashed passwords we truncated inputs to 72 bytes, so apply the
    # same truncation before verification to ensure the check succeeds.
    if plain_password is None:
        return False

    pw_bytes = plain_password.encode("utf-8")[:72]
    safe_password = pw_bytes.decode("utf-8", errors="ignore")
    return pwd_context.verify(safe_password, hashed_password)


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
