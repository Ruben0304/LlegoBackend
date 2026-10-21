"""GraphQL mutations for authentication."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import auth_repo
from utils.auth import (
    create_access_token,
    get_apple_private_email,
    verify_apple,
    verify_google,
)
from utils.client_ip import get_client_ip
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import check_rate_limit


def _frenar_intentos(info: Info, email: str) -> None:
    """Límite de intentos de login/registro por IP y por correo (antes no había ninguno)."""
    ctx = info.context
    request = ctx.get("request") if isinstance(ctx, dict) else getattr(ctx, "request", None)
    ip_ok, _ = check_rate_limit(get_client_ip(request), "login_ip")
    correo_ok, _ = check_rate_limit((email or "").strip().lower(), "login_email")
    if not (ip_ok and correo_ok):
        raise Exception("Demasiados intentos. Espera un minuto y vuelve a probar.")

from .types import (
    AppleLoginInput,
    AuthResponse,
    LoginInput,
    RegisterInput,
    SocialLoginInput,
    UserData,
)


@strawberry.type
class AuthMutation:
    @strawberry.mutation(description="Register a new user")
    async def register(
        self, info: Info, input: RegisterInput, jwt: Optional[str] = None
    ) -> AuthResponse:
        """Register a new user with email and password. Role is always 'customer'."""
        apply_optional_jwt(jwt, info)
        _frenar_intentos(info, input.email)
        # El correo se guarda en minúsculas y se busca sin distinguirlas: antes
        # «Ana@x.com» creaba una cuenta distinta de «ana@x.com»
        email = input.email.strip().lower()
        existing_user = await auth_repo.get_user_by_email(email)
        if existing_user:
            raise Exception("Email already registered")

        # Create new user - role is ALWAYS "customer", never from input
        user = await auth_repo.create_user(
            name=input.name,
            email=email,
            password=input.password,
            phone=input.phone,
            role="customer",  # Hardcoded - only changeable via DB
        )

        # Create access token with role
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id), "role": user.role}
        )

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=str(user.id),
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat(),
            ),
        )

    @strawberry.mutation(description="Login with email and password")
    async def login(
        self, info: Info, input: LoginInput, jwt: Optional[str] = None
    ) -> AuthResponse:
        """Login with email and password."""
        apply_optional_jwt(jwt, info)
        _frenar_intentos(info, input.email)
        user = await auth_repo.authenticate_user(input.email.strip(), input.password)
        if not user:
            raise Exception("Invalid email or password")

        # Create access token with role
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id), "role": user.role}
        )

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=str(user.id),
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat(),
            ),
        )

    @strawberry.mutation(description="Login with Google")
    async def login_with_google(
        self, info: Info, input: SocialLoginInput, jwt: Optional[str] = None
    ) -> AuthResponse:
        """Login with Google ID token."""
        apply_optional_jwt(jwt, info)
        # Verify token
        token_info = verify_google(input.id_token, input.nonce)

        # Create or update user
        user = await auth_repo.upsert_social_user(
            email=token_info["email"],
            provider="google",
            provider_user_id=token_info["sub"],
            name=token_info["name"],
        )

        # Create access token with role
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id), "role": user.role}
        )

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=str(user.id),
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat(),
            ),
        )

    @strawberry.mutation(description="Login with Apple")
    async def login_with_apple(
        self, info: Info, input: AppleLoginInput, jwt: Optional[str] = None
    ) -> AuthResponse:
        """Login with Apple Identity token."""
        apply_optional_jwt(jwt, info)
        # Verify token
        token_info = verify_apple(input.identity_token, input.nonce)

        # Create or update user
        user = await auth_repo.upsert_social_user(
            email=token_info["email"],
            provider="apple",
            provider_user_id=token_info["sub"],
            apple_private_email=get_apple_private_email(
                token_info.get("email"), token_info.get("is_private_email")
            ),
        )

        # Create access token with role
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id), "role": user.role}
        )

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=str(user.id),
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat(),
            ),
        )
