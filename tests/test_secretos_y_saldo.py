"""Fase 0 de la auditoría (21 oct 2026): nada de secretos en endpoints públicos ni
saldo creado por el cliente.

- `GET /stripe/config` servía la clave secreta (`sk_live_`) porque la variable de la
  publicable la tenía puesta. Ahora solo sirve claves `pk_`.
- `depositMoney` acreditaba saldo a cualquier sesión, sin pasarela.
- `/health/redis` devolvía parte de la URL de Redis, contraseña incluida.
- Ningún archivo del repo lleva la URL de la base de producción.
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.endpoints.stripe_payments as stripe_payments
import schema.wallet.mutations as wallet_mutations
import utils.rate_limit as rate_limit
from core.config import settings
from utils.auth import create_access_token

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def jwt_secret():
    with patch.object(settings, "jwt_secret", "test-jwt-secret-fase0"):
        yield


def _cliente_stripe():
    app = FastAPI()
    app.include_router(stripe_payments.router)
    return TestClient(app)


@pytest.mark.parametrize("clave", ["sk_live_abc", "sk_test_abc", "rk_live_abc", "", "  "])
def test_stripe_config_no_sirve_claves_que_no_son_publicables(clave):
    with patch.object(settings, "stripe_publishable_key", clave):
        r = _cliente_stripe().get("/stripe/config")
    assert r.status_code == 503
    assert "sk_" not in r.text and "rk_" not in r.text


def test_stripe_config_sirve_la_publicable():
    with patch.object(settings, "stripe_publishable_key", " pk_live_123 "):
        r = _cliente_stripe().get("/stripe/config")
    assert r.status_code == 200
    assert r.json() == {"publishable_key": "pk_live_123"}


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _token(role: str) -> str:
    return create_access_token({"user_id": "507f1f77bcf86cd799439011", "role": role})


@pytest.mark.parametrize("role", ["customer", "manager", "delivery", "risk_admin"])
def test_deposit_money_rechaza_a_quien_no_es_admin(monkeypatch, role):
    deposito = AsyncMock()
    monkeypatch.setattr(wallet_mutations, "wallet_service", SimpleNamespace(deposit=deposito))
    entrada = SimpleNamespace(amount=1_000_000, currency="usd", source="prueba", description=None)
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(wallet_mutations.WalletMutation().deposit_money(info=_info(), input=entrada, jwt=_token(role)))
    deposito.assert_not_awaited()


def test_deposit_money_sin_sesion(monkeypatch):
    deposito = AsyncMock()
    monkeypatch.setattr(wallet_mutations, "wallet_service", SimpleNamespace(deposit=deposito))
    entrada = SimpleNamespace(amount=10, currency="usd", source="prueba", description=None)
    with pytest.raises(Exception, match="Autenticación requerida"):
        asyncio.run(wallet_mutations.WalletMutation().deposit_money(info=_info(), input=entrada, jwt=None))
    deposito.assert_not_awaited()


def test_health_redis_no_muestra_la_url(monkeypatch):
    falso = MagicMock()
    falso.info.return_value = {"redis_version": "7.2"}
    monkeypatch.setattr(rate_limit, "redis_client", falso)
    monkeypatch.setattr(settings, "redis_url", "redis://default:secreto123@redis.internal:6379")
    estado = rate_limit.get_redis_status()
    assert estado == {"connected": True, "version": "7.2"}

    falso.ping.side_effect = ConnectionError("redis://default:secreto123@redis.internal:6379 caído")
    estado = rate_limit.get_redis_status()
    assert "secreto123" not in str(estado)
    assert estado["connected"] is False


def test_ningun_archivo_versionado_lleva_credenciales_de_mongo():
    archivos = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.split()
    patron = re.compile(r"mongodb(\+srv)?://[^\s:/@\"'$]+:[^\s@\"'$]+@")
    culpables = []
    for nombre in archivos:
        ruta = RAIZ / nombre
        if nombre.endswith(".example") or not ruta.is_file():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if patron.search(texto):
            culpables.append(nombre)
    assert culpables == []
