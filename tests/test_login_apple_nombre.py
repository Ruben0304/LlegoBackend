"""loginWithApple guarda el nombre que Apple da solo la primera vez (fullName opcional)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import schema.auth.mutations as mutations
from schema.auth.types import AppleLoginInput


def _login(monkeypatch, full_name):
    monkeypatch.setattr(
        mutations, "verify_apple", lambda token, nonce: {"email": "x@privaterelay.appleid.com", "sub": "s1"}
    )
    usuario = SimpleNamespace(
        id="u1", email="x@privaterelay.appleid.com", name="Ana Pérez", phone=None, role="customer",
        createdAt=SimpleNamespace(isoformat=lambda: "2026-10-22T00:00:00"),
    )
    upsert = AsyncMock(return_value=usuario)
    monkeypatch.setattr(mutations.auth_repo, "upsert_social_user", upsert)
    entrada = AppleLoginInput(identity_token="t", nonce="n", full_name=full_name)
    asyncio.run(mutations.AuthMutation.login_with_apple(None, SimpleNamespace(context={}), entrada))
    return upsert.await_args.kwargs["name"]


def test_usa_el_nombre_que_manda_la_app(monkeypatch):
    assert _login(monkeypatch, "  Ana Pérez ") == "Ana Pérez"


def test_sin_nombre_no_se_inventa(monkeypatch):
    assert _login(monkeypatch, None) is None
    assert _login(monkeypatch, "   ") is None
