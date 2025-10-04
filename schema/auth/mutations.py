"""GraphQL mutations for authentication."""
import strawberry
from typing import Optional

from .types import AuthResponse, RegisterInput, LoginInput, UserData
from repositories import auth_repo
from utils.auth import create_access_token


@strawberry.type
class AuthMutation:
    @strawberry.mutation(description="Register a new user")
    async def register(self, input: RegisterInput) -> AuthResponse:
        """Register a new user with email and password."""
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
    async def login(self, input: LoginInput) -> AuthResponse:
        """Login with email and password."""
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
