"""Authentication repository for user login and registration."""
from motor.motor_asyncio import AsyncIOMotorDatabase
from models import User
from utils.auth import hash_password, verify_password
from datetime import datetime
from typing import Optional


class AuthRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["users"]

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        user_data = await self.collection.find_one({"email": email})
        if user_data:
            user_data["_id"] = str(user_data["_id"])
            return User(**user_data)
        return None

    async def create_user(
        self, name: str, email: str, password: str, phone: Optional[str] = None, role: str = "customer"
    ) -> User:
        """Create a new user with hashed password."""
        hashed_password = hash_password(password)

        user_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_password,
            "role": role,
            "createdAt": datetime.utcnow(),
        }

        result = await self.collection.insert_one(user_data)
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
