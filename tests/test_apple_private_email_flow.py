import importlib.util
import os
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bson import ObjectId

# Minimal env required by core.config.Settings at import time
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

from utils.auth import get_apple_private_email


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUsersCollection:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def update_one(self, filter_query, update_query):
        target_id = filter_query.get("_id")
        for doc in self.docs:
            if doc.get("_id") == target_id:
                doc.update(update_query.get("$set", {}))
                break

    async def insert_one(self, doc):
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = ObjectId()
        self.docs.append(new_doc)
        return FakeInsertResult(new_doc["_id"])


class FakeDB:
    def __init__(self, users_collection):
        self.users_collection = users_collection

    def __getitem__(self, name):
        if name != "users":
            raise KeyError(name)
        return self.users_collection


def load_auth_repository_class():
    """Load auth_repository.py without importing repositories package."""
    fake_clients = types.ModuleType("clients")

    def _placeholder_get_database():
        raise RuntimeError("get_database should be patched in tests")

    fake_clients.get_database = _placeholder_get_database
    sys.modules["clients"] = fake_clients

    module_path = (
        Path(__file__).resolve().parents[1] / "repositories" / "auth_repository.py"
    )
    spec = importlib.util.spec_from_file_location(
        "auth_repository_under_test", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.AuthRepository, module


class TestApplePrivateEmailFlow(unittest.IsolatedAsyncioTestCase):
    def test_private_relay_email_is_kept(self):
        value = get_apple_private_email("relay@privaterelay.appleid.com", True)
        self.assertEqual(value, "relay@privaterelay.appleid.com")

    def test_non_private_email_sets_none(self):
        value = get_apple_private_email("normal@example.com", False)
        self.assertIsNone(value)

    def test_missing_email_sets_none(self):
        value = get_apple_private_email(None, True)
        self.assertIsNone(value)

    async def test_upsert_create_normalizes_boolean_private_email(self):
        AuthRepository, auth_repo_module = load_auth_repository_class()
        users_collection = FakeUsersCollection(docs=[])
        fake_db = FakeDB(users_collection)

        repo = AuthRepository()
        with patch.object(auth_repo_module, "get_database", return_value=fake_db):
            user = await repo.upsert_social_user(
                email="normal@example.com",
                provider="apple",
                provider_user_id="sub-1",
                apple_private_email=True,
            )

        self.assertEqual(user.email, "normal@example.com")
        self.assertIsNone(user.applePrivateEmail)

    async def test_upsert_update_normalizes_boolean_private_email(self):
        AuthRepository, auth_repo_module = load_auth_repository_class()
        existing_id = ObjectId()
        users_collection = FakeUsersCollection(
            docs=[
                {
                    "_id": existing_id,
                    "name": "User",
                    "email": "normal@example.com",
                    "username": "normal",
                    "createdAt": datetime.utcnow(),
                    "authProvider": "local",
                    "providerUserId": None,
                }
            ]
        )
        fake_db = FakeDB(users_collection)

        repo = AuthRepository()
        with patch.object(auth_repo_module, "get_database", return_value=fake_db):
            user = await repo.upsert_social_user(
                email="normal@example.com",
                provider="apple",
                provider_user_id="sub-2",
                apple_private_email=False,
            )

        self.assertEqual(str(user.id), str(existing_id))
        self.assertIsNone(user.applePrivateEmail)

    async def test_upsert_existing_provider_without_email_does_not_fail(self):
        AuthRepository, auth_repo_module = load_auth_repository_class()
        existing_id = ObjectId()
        users_collection = FakeUsersCollection(
            docs=[
                {
                    "_id": existing_id,
                    "name": "Relay User",
                    "email": "relay@privaterelay.appleid.com",
                    "username": "relay",
                    "createdAt": datetime.utcnow(),
                    "authProvider": "apple",
                    "providerUserId": "apple-sub-existing",
                    "applePrivateEmail": "relay@privaterelay.appleid.com",
                }
            ]
        )
        fake_db = FakeDB(users_collection)

        repo = AuthRepository()
        with patch.object(auth_repo_module, "get_database", return_value=fake_db):
            user = await repo.upsert_social_user(
                email=None,
                provider="apple",
                provider_user_id="apple-sub-existing",
                apple_private_email=None,
            )

        self.assertEqual(str(user.id), str(existing_id))
        self.assertEqual(user.applePrivateEmail, "relay@privaterelay.appleid.com")

    async def test_upsert_existing_provider_with_historical_bool_is_sanitized(self):
        AuthRepository, auth_repo_module = load_auth_repository_class()
        existing_id = ObjectId()
        users_collection = FakeUsersCollection(
            docs=[
                {
                    "_id": existing_id,
                    "name": "Legacy User",
                    "email": "legacy@example.com",
                    "username": "legacy",
                    "createdAt": datetime.utcnow(),
                    "authProvider": "apple",
                    "providerUserId": "apple-sub-legacy",
                    "applePrivateEmail": True,
                }
            ]
        )
        fake_db = FakeDB(users_collection)

        repo = AuthRepository()
        with patch.object(auth_repo_module, "get_database", return_value=fake_db):
            user = await repo.upsert_social_user(
                email=None,
                provider="apple",
                provider_user_id="apple-sub-legacy",
                apple_private_email=None,
            )

        self.assertEqual(str(user.id), str(existing_id))
        self.assertIsNone(user.applePrivateEmail)
        self.assertIsNone(users_collection.docs[0]["applePrivateEmail"])

    async def test_upsert_email_link_path_with_historical_bool_is_sanitized(self):
        AuthRepository, auth_repo_module = load_auth_repository_class()
        existing_id = ObjectId()
        users_collection = FakeUsersCollection(
            docs=[
                {
                    "_id": existing_id,
                    "name": "Email Link User",
                    "email": "emaillink@example.com",
                    "username": "emaillink",
                    "createdAt": datetime.utcnow(),
                    "authProvider": "local",
                    "providerUserId": None,
                    "applePrivateEmail": False,
                }
            ]
        )
        fake_db = FakeDB(users_collection)

        repo = AuthRepository()
        with patch.object(auth_repo_module, "get_database", return_value=fake_db):
            user = await repo.upsert_social_user(
                email="emaillink@example.com",
                provider="apple",
                provider_user_id="apple-sub-new",
                apple_private_email=None,
            )

        self.assertEqual(str(user.id), str(existing_id))
        self.assertIsNone(user.applePrivateEmail)
        self.assertIsNone(users_collection.docs[0]["applePrivateEmail"])


if __name__ == "__main__":
    unittest.main()
