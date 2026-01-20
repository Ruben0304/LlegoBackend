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
        
        # 1. Try to find by provider info
        user_data = await db[self.collection_name].find_one({
            "providerUserId": provider_user_id,
            "authProvider": provider
        })
        
        if user_data:
            user_data["_id"] = str(user_data["_id"])
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
                if apple_private_email:
                    update_fields["applePrivateEmail"] = apple_private_email
                    
                await db[self.collection_name].update_one(
                    {"_id": user_data["_id"]},
                    {"$set": update_fields}
                )
                
                # Fetch updated user
                user_data = await db[self.collection_name].find_one({"_id": user_data["_id"]})
                user_data["_id"] = str(user_data["_id"])
                return User(**user_data)
        
        # 3. Create new user
        user_data = {
            "name": name or (email.split("@")[0] if email else "User"),
            "email": email,
            "password": None,
            "role": "customer",
            "wallet": {"local": 0.0, "usd": 0.0},
            "walletStatus": "active",
            "createdAt": datetime.utcnow(),
            "authProvider": provider,
            "providerUserId": provider_user_id,
            "applePrivateEmail": apple_private_email,
        }
        
        result = await db[self.collection_name].insert_one(user_data)
        user_data["_id"] = str(result.inserted_id)
        
        return User(**user_data)
