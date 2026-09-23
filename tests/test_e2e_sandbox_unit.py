"""Garantias del sandbox E2E verificadas en proceso (sin red ni BD)."""

import asyncio
import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest

import clients.mongodb_client as mongodb_client
from core import sandbox
from core.config import settings
from utils.auth import create_access_token, decode_access_token


@pytest.fixture
def sandbox_settings(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "prod-secret")
    monkeypatch.setattr(settings, "e2e_sandbox_key", "k" * 32)
    monkeypatch.setattr(settings, "e2e_database", "")
    monkeypatch.setattr(settings, "mongodb_database", "llego")


def _in_sandbox(fn):
    token = sandbox.activate()
    try:
        return fn()
    finally:
        sandbox.deactivate(token)


def test_disabled_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "e2e_sandbox_key", "")
    assert not sandbox.sandbox_enabled()
    assert not sandbox.key_matches("")
    assert not sandbox.key_matches("anything")


def test_key_must_match_exactly(sandbox_settings):
    assert sandbox.key_matches("k" * 32)
    assert not sandbox.key_matches("k" * 31)
    assert not sandbox.key_matches(None)


def test_sandbox_tokens_are_useless_in_production_and_vice_versa(sandbox_settings):
    prod_token = create_access_token({"user_id": "u1", "role": "admin"})
    sandbox_token = _in_sandbox(lambda: create_access_token({"user_id": "u1", "role": "admin"}))

    assert decode_access_token(prod_token)["user_id"] == "u1"
    assert decode_access_token(sandbox_token) is None  # sandbox -> prod: rechazado
    assert _in_sandbox(lambda: decode_access_token(prod_token)) is None  # prod -> sandbox
    assert _in_sandbox(lambda: decode_access_token(sandbox_token))["user_id"] == "u1"


def test_sandbox_database_can_never_be_production(sandbox_settings, monkeypatch):
    assert sandbox.sandbox_database_name() == "llego_e2e"
    monkeypatch.setattr(settings, "e2e_database", "llego")
    with pytest.raises(sandbox.SandboxConfigError):
        sandbox.sandbox_database_name()
    with pytest.raises(sandbox.SandboxConfigError):
        sandbox.activate()
    assert not sandbox.is_sandbox()


def test_get_database_switches_only_inside_sandbox(sandbox_settings, monkeypatch):
    class FakeClient(dict):
        def __missing__(self, name):
            return f"db:{name}"

    monkeypatch.setattr(mongodb_client, "mongo_client", FakeClient())
    monkeypatch.setattr(mongodb_client, "database", "db:llego")

    assert mongodb_client.get_database() == "db:llego"
    assert _in_sandbox(mongodb_client.get_database) == "db:llego_e2e"
    assert mongodb_client.get_database() == "db:llego"


def test_sandbox_flag_does_not_leak_between_concurrent_requests(sandbox_settings):
    seen = {}

    async def request(name, use_sandbox):
        token = sandbox.activate() if use_sandbox else None
        try:
            await asyncio.sleep(0.01)
            seen[name] = sandbox.is_sandbox()
        finally:
            if token:
                sandbox.deactivate(token)

    async def main():
        await asyncio.gather(request("e2e", True), request("prod", False))

    asyncio.run(main())
    assert seen == {"e2e": True, "prod": False}


def test_cache_is_disabled_inside_sandbox(sandbox_settings, monkeypatch):
    from utils import cache

    monkeypatch.setattr(settings, "cache_enabled", True)
    assert cache.is_cache_enabled()
    assert _in_sandbox(cache.is_cache_enabled) is False
