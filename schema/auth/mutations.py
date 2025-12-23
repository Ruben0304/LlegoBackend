"""GraphQL mutations for authentication."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import AuthResponse, RegisterInput, LoginInput, UserData, SocialLoginInput, AppleLoginInput
from repositories import auth_repo
from utils.auth import create_access_token, verify_google, verify_apple
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class AuthMutation:
    @strawberry.mutation(description="Register a new user")
    async def register(
        self,
        info: Info,
        input: RegisterInput,
        jwt: Optional[str] = None
    ) -> AuthResponse:
        """Register a new user with email and password."""
        apply_optional_jwt(jwt, info)
        # Check if user already exists
        existing_user = await auth_repo.get_user_by_email(input.email)
        if existing_user:
            raise Exception("Email already registered")

        # Create new user
        user = await auth_repo.create_user(
            name=input.name,
            email=input.email,
            password=input.password,
            phone=input.phone,
            role=input.role or "customer"
        )

        # Create access token
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat()
            )
        )

    @strawberry.mutation(description="Login with email and password")
    async def login(self, info: Info, input: LoginInput, jwt: Optional[str] = None) -> AuthResponse:
        """Login with email and password."""
        apply_optional_jwt(jwt, info)
        # Authenticate user
        user = await auth_repo.authenticate_user(input.email, input.password)
        if not user:
            raise Exception("Invalid email or password")

        # Create access token
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat()
            )
        )


    @strawberry.mutation(description="Login with Google")
    async def login_with_google(
        self,
        info: Info,
        input: SocialLoginInput,
        jwt: Optional[str] = None
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
            name=token_info["name"]
        )
        
        # Create access token
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
        
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat()
            )
        )

    @strawberry.mutation(description="Login with Apple")
    async def login_with_apple(
        self,
        info: Info,
        input: AppleLoginInput,
        jwt: Optional[str] = None
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
            apple_private_email=token_info["is_private_email"]
        )
        
        # Create access token
        access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
        
        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserData(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                role=user.role,
                created_at=user.createdAt.isoformat()
            )
        )
