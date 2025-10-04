"""GraphQL types for authentication."""
import strawberry
from typing import Optional


@strawberry.input
class RegisterInput:
    name: str
    email: str
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "customer"


@strawberry.input
class LoginInput:
    email: str
    password: str


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
