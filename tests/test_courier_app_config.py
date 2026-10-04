"""courierAppConfig: versiones y mantenimiento de la app de choferes.

Mismo contrato que businessAppConfig (minVersion/currentVersion por plataforma
y modo mantenimiento). AppMensajeros la consulta al arrancar para bloquear
versiones viejas o mostrar mantenimiento; si devuelve null no bloquea nada.
"""

import asyncio
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
from bson import ObjectId
from graphql import parse, validate

import repositories.app_config_repository as config_repo_module
import schema.app_config.mutations as config_mutations
import schema.app_config.queries as config_queries
from core.config import settings
from repositories.app_config_repository import CourierAppConfigRepository
from schema.app_config.inputs import (
    UpdateAndroidConfigInput,
    UpdateAppConfigInput,
    UpdateMaintenanceConfigInput,
)
from schema.schema import schema as graphql_schema
from utils.auth import create_access_token

# Lo que pide AppMensajeros (shared/src/commonMain/graphql/config/CourierAppConfig.graphql).
COURIER_APP_OPERATION = """
query CourierAppConfig {
  courierAppConfig {
    android { minVersion currentVersion storeUrl updateUrl }
    ios { minVersion currentVersion storeUrl }
    maintenance { enabled message }
    updateMessage
  }
}
"""


class FakeCollection:
    """Colección Mongo en memoria con lo que usa CourierAppConfigRepository."""

    def __init__(self):
        self.docs = []

    async def find_one(self, *args, **kwargs):
        return dict(self.docs[0]) if self.docs else None

    async def insert_one(self, doc):
        doc = dict(doc)
        doc["_id"] = ObjectId()
        self.docs.append(doc)
        return MagicMock(inserted_id=doc["_id"])

    async def find_one_and_update(self, query, update, return_document=True):
        for doc in self.docs:
            if str(doc["_id"]) == str(query["_id"]):
                doc.update(update["$set"])
                return dict(doc)
        return None


@pytest.fixture
def collection(monkeypatch):
    coll = FakeCollection()
    monkeypatch.setattr(config_repo_module, "get_database", lambda: {"courier_app_config": coll})
    cache = {}
    monkeypatch.setattr(config_repo_module, "get_cached", lambda key: cache.get(key))
    monkeypatch.setattr(config_repo_module, "set_cached", lambda key, value: cache.__setitem__(key, value))
    monkeypatch.setattr(config_repo_module, "invalidate_cache", lambda key: cache.pop(key, None))
    repo = CourierAppConfigRepository()
    monkeypatch.setattr(config_queries, "courier_app_config_repo", repo)
    monkeypatch.setattr(config_mutations, "courier_app_config_repo", repo)
    return coll


@pytest.fixture(autouse=True)
def jwt_secret():
    with patch.object(settings, "jwt_secret", "test-jwt-secret-courier-config"):
        yield


def _token(role: str) -> str:
    return create_access_token({"user_id": "507f1f77bcf86cd799439011", "role": role})


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def run(coro):
    return asyncio.run(coro)


def test_courier_app_operation_validates_against_schema():
    assert validate(graphql_schema._schema, parse(COURIER_APP_OPERATION)) == []


def test_query_returns_null_until_configured(collection):
    assert run(config_queries.AppConfigQueries().courier_app_config()) is None


@pytest.mark.parametrize("role", ["customer", "manager"])
def test_update_requires_admin(collection, role):
    with pytest.raises(Exception, match="Acceso denegado"):
        run(
            config_mutations.AppConfigMutations().update_courier_app_config(
                info=_info(), input=UpdateAppConfigInput(), jwt=_token(role)
            )
        )
    assert collection.docs == []


def test_first_update_creates_default_config_then_applies_changes(collection):
    result = run(
        config_mutations.AppConfigMutations().update_courier_app_config(
            info=_info(),
            input=UpdateAppConfigInput(
                android=UpdateAndroidConfigInput(min_version="1.2", store_url="https://play/x"),
                maintenance=UpdateMaintenanceConfigInput(enabled=True, message="Volvemos pronto"),
            ),
            jwt=_token("admin"),
        )
    )

    assert len(collection.docs) == 1
    assert result.android.min_version == "1.2"
    assert result.android.current_version == "0.0.0"  # valor inicial, no bloquea
    assert result.android.store_url == "https://play/x"
    assert result.ios.min_version == "0.0.0"
    assert result.maintenance.enabled is True
    assert result.maintenance.message == "Volvemos pronto"

    # La query pública ya devuelve lo guardado (y la caché queda al día).
    fetched = run(config_queries.AppConfigQueries().courier_app_config())
    assert fetched.android.min_version == "1.2"
    assert fetched.maintenance.enabled is True


def test_update_without_fields_is_rejected(collection):
    with pytest.raises(Exception, match="No hay campos"):
        run(
            config_mutations.AppConfigMutations().update_courier_app_config(
                info=_info(), input=UpdateAppConfigInput(), jwt=_token("admin")
            )
        )


def test_partial_update_keeps_other_fields(collection):
    mutation = config_mutations.AppConfigMutations()
    run(
        mutation.update_courier_app_config(
            info=_info(),
            input=UpdateAppConfigInput(android=UpdateAndroidConfigInput(current_version="1.5")),
            jwt=_token("admin"),
        )
    )
    result = run(
        mutation.update_courier_app_config(
            info=_info(),
            input=UpdateAppConfigInput(
                android=UpdateAndroidConfigInput(min_version="1.1"),
                release_date=datetime(2026, 10, 2),
            ),
            jwt=_token("admin"),
        )
    )
    assert result.android.current_version == "1.5"
    assert result.android.min_version == "1.1"
    assert result.release_date == datetime(2026, 10, 2)
