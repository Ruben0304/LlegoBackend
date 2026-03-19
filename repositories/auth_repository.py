"""Authentication repository for user login and registration."""

import logging
from datetime import datetime
from typing import Optional

from clients import get_database
from domain.models import User
from utils.auth import hash_password, verify_password


class AuthRepository:
    collection_name = "users"
    logger = logging.getLogger(__name__)

    @staticmethod
    def _normalize_apple_private_email(value: Optional[object]) -> Optional[str]:
        """Normalize relay email value to Optional[str], rejecting booleans and invalid data."""
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return None

    def _sanitize_user_data_apple_private_email(self, user_data: dict) -> dict:
        """Ensure applePrivateEmail in user_data is always Optional[str] before User(**user_data)."""
        current = user_data.get("applePrivateEmail")
        normalized = self._normalize_apple_private_email(current)
        user_data["applePrivateEmail"] = normalized
        self.logger.info(
            "[auth] applePrivateEmail before User(): value=%r type=%s",
            normalized,
            type(normalized).__name__,
        )
        return user_data

    async def _persist_apple_private_email_if_changed(
        self,
        db,
        doc_id,
        original_value: Optional[object],
        normalized_value: Optional[str],
    ) -> None:
        """Persist sanitized applePrivateEmail only when historical data needs correction."""
        if original_value != normalized_value:
            await db[self.collection_name].update_one(
                {"_id": doc_id},
                {"$set": {"applePrivateEmail": normalized_value}},
            )

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        db = get_database()
        user_data = await db[self.collection_name].find_one({"email": email})
        if user_data:
            user_data["_id"] = str(user_data["_id"])
            user_data = self._sanitize_user_data_apple_private_email(user_data)
            return User(**user_data)
        return None

    async def create_user(
        self,
        name: str,
        email: str,
        password: str,
        phone: Optional[str] = None,
        role: str = "customer",
    ) -> User:
        """Create a new user with hashed password."""
        db = get_database()
        hashed_password = hash_password(password)

        # Generate username from email (part before @)
        username = email.split("@")[0]

        # Ensure username is unique by appending numbers if needed
        base_username = username
        counter = 1
        while await db[self.collection_name].find_one({"username": username}):
            username = f"{base_username}{counter}"
            counter += 1

        user_data = {
            "name": name,
            "email": email,
            "username": username,
            "phone": phone,
            "password": hashed_password,
            "role": role,
            "isPro": False,
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
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

    async def upsert_social_user(
        self,
        email: str,
        provider: str,
        provider_user_id: str,
        name: Optional[str] = None,
        apple_private_email: Optional[str] = None,
    ) -> User:
        """
        Create a new user or return an existing one based on provider info.
        If a user with the same email exists, link the account.
        """
        db = get_database()
        normalized_apple_private_email = self._normalize_apple_private_email(
            apple_private_email
        )

        # 1. Try to find by provider info
        user_data = await db[self.collection_name].find_one(
            {"providerUserId": provider_user_id, "authProvider": provider}
        )

        if user_data:
            doc_id = user_data["_id"]
            original_apple_private_email = user_data.get("applePrivateEmail")
            user_data = self._sanitize_user_data_apple_private_email(user_data)
            await self._persist_apple_private_email_if_changed(
                db,
                doc_id,
                original_apple_private_email,
                user_data.get("applePrivateEmail"),
            )
            user_data["_id"] = str(doc_id)
            return User(**user_data)

        # 2. Try to find by email (linking account)
        if email:
            user_data = await db[self.collection_name].find_one({"email": email})
            if user_data:
                # Link account: Update provider info
                # We update the provider fields so next time we find by providerUserId
                update_fields = {
                    "providerUserId": provider_user_id,
                    # We might want to keep the original authProvider/password if it was local/other
                    # But the prompt says "guarda siempre sub + iss".
                    # We'll just add providerUserId. The authProvider field might be 'local' still.
                    # This is simple linking.
                }
                if normalized_apple_private_email:
                    update_fields["applePrivateEmail"] = normalized_apple_private_email

                await db[self.collection_name].update_one(
                    {"_id": user_data["_id"]}, {"$set": update_fields}
                )

                # Fetch updated user
                user_data = await db[self.collection_name].find_one(
                    {"_id": user_data["_id"]}
                )
                doc_id = user_data["_id"]
                original_apple_private_email = user_data.get("applePrivateEmail")
                user_data = self._sanitize_user_data_apple_private_email(user_data)
                await self._persist_apple_private_email_if_changed(
                    db,
                    doc_id,
                    original_apple_private_email,
                    user_data.get("applePrivateEmail"),
                )
                user_data["_id"] = str(doc_id)
                return User(**user_data)

        # 3. Create new user
        # Generate username from email (part before @)
        username = email.split("@")[0] if email else "user"

        # Ensure username is unique by appending numbers if needed
        base_username = username
        counter = 1
        while await db[self.collection_name].find_one({"username": username}):
            username = f"{base_username}{counter}"
            counter += 1

        user_data = {
            "name": name or (email.split("@")[0] if email else "User"),
            "email": email,
            "username": username,
            "password": None,
            "role": "customer",
            "isPro": False,
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
            "createdAt": datetime.utcnow(),
            "authProvider": provider,
            "providerUserId": provider_user_id,
            "applePrivateEmail": normalized_apple_private_email,
        }

        result = await db[self.collection_name].insert_one(user_data)
        user_data["_id"] = str(result.inserted_id)
        user_data = self._sanitize_user_data_apple_private_email(user_data)

        return User(**user_data)
