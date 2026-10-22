"""GraphQL types for authentication."""
import strawberry
from typing import Optional


@strawberry.input
class RegisterInput:
    name: str
    email: str
    password: str
    phone: Optional[str] = None
    # role is NOT accepted from input - always defaults to "customer"


@strawberry.input
class LoginInput:
    email: str
    password: str


@strawberry.input
class SocialLoginInput:
    id_token: str
    authorization_code: Optional[str] = None
    nonce: Optional[str] = None


@strawberry.input
class AppleLoginInput:
    identity_token: str
    authorization_code: Optional[str] = None
    nonce: Optional[str] = None
    # Apple solo da el nombre la primera vez que alguien entra, y no va en el token: la app
    # lo manda aquí para la cuenta nueva (si no, el nombre sale del correo, a menudo privado).
    full_name: Optional[str] = None


@strawberry.type
class UserData:
    id: str
    name: str
    email: str
    phone: Optional[str]
    role: str
    created_at: str


@strawberry.type
class AuthResponse:
    access_token: str
    token_type: str
    user: UserData
