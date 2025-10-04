"""Authentication repository for user login and registration."""
from clients import get_database
from models import User
from utils.auth import hash_password, verify_password
from datetime import datetime
from typing import Optional


class AuthRepository:
    collection_name = "users"

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        db = get_database()
        user_data = await db[self.collection_name].find_one({"email": email})
        if user_data:
            user_data["_id"] = str(user_data["_id"])
            return User(**user_data)
        return None

    async def create_user(
        self, name: str, email: str, password: str, phone: Optional[str] = None, role: str = "customer"
    ) -> User:
        """Create a new user with hashed password."""
        db = get_database()
        hashed_password = hash_password(password)

        user_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_password,
            "role": role,
            "createdAt": datetime.utcnow(),
        }

        result = await db[self.collection_name].insert_one(user_data)
        user_data["_id"] = str(result.inserted_id)

        return User(**user_data)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None

        if not verify_password(password, user.password):
            return None

        return user
