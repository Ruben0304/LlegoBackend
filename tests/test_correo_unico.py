"""Índice único de users.email: el registro y el login social manejan el choque."""
import asyncio
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from repositories import auth_repository as modulo
from repositories.auth_repository import AuthRepository


class _Usuarios:
    """Colección mínima: el primer insert choca (otra petición creó la cuenta a la vez)."""

    def __init__(self, existente=None):
        self.existente = existente
        self.inserts = 0

    async def find_one(self, filtro):
        if self.existente and ("email" in filtro or filtro.get("_id") == self.existente["_id"]):
            return dict(self.existente)
        return None

    async def insert_one(self, doc):
        self.inserts += 1
        raise DuplicateKeyError("E11000 idx_users_email_unico")

    async def update_one(self, *a, **k):
        return None


def _base(usuarios):
    return {"users": usuarios}


def test_registro_simultaneo_con_el_mismo_correo():
    with patch.object(modulo, "get_database", return_value=_base(_Usuarios())):
        with pytest.raises(Exception, match="Email already registered"):
            asyncio.run(AuthRepository().create_user(
                name="Ana", email="ana@x.com", password="Secreta123!", phone=None, role="customer"
            ))


def test_login_social_que_choca_se_enlaza_a_la_cuenta_creada():
    cuenta = {"_id": ObjectId(), "email": "Ana@x.com", "name": "Ana", "username": "ana",
              "role": "customer", "wallet": {"local": 0.0, "usd": 0.0}, "walletStatus": "active",
              "createdAt": __import__("datetime").datetime(2026, 1, 1)}
    usuarios = _Usuarios(existente=cuenta)

    async def correo_tras_choque(email):
        # Antes del insert no hay cuenta; tras el choque, sí (la creó la otra petición)
        return dict(cuenta) if usuarios.inserts else None

    repo = AuthRepository()
    with patch.object(modulo, "get_database", return_value=_base(usuarios)), \
            patch.object(repo, "_documento_por_correo", side_effect=correo_tras_choque):
        usuario = asyncio.run(repo.upsert_social_user(
            email="ana@x.com", provider="google", provider_user_id="g-1"
        ))
    assert str(usuario.id) == str(cuenta["_id"])
    assert usuarios.inserts == 1
