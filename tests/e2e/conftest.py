"""Configuracion de la suite E2E.

Corre contra un backend real (local o desplegado) a traves de la API publica,
dentro del sandbox E2E: nada toca los datos de produccion (ver core/sandbox.py).

Variables de entorno:
  E2E_KEY       (obligatoria) igual a E2E_SANDBOX_KEY del backend. Sin ella la
                suite se salta completa.
  E2E_BASE_URL  (opcional) por defecto http://127.0.0.1:8000
  E2E_DROP_SANDBOX=1  (opcional) borra la BD del sandbox al terminar.
"""

import os

import httpx
import pytest

from .client import SANDBOX_HEADER, E2EClient
from .flows import World


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "pagos: suite de pagos (la mas importante): cobros, confirmaciones, "
        "reintentos, timeouts con dinero y permisos sobre pagos",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("E2E_KEY"):
        return
    skip = pytest.mark.skip(reason="E2E_KEY no definida: suite E2E deshabilitada")
    for item in items:
        if "tests/e2e/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def client():
    client = E2EClient.from_env()
    # Barrera de seguridad antes de cualquier escritura: el backend debe
    # confirmar que esta en modo sandbox y que la BD no es la de produccion.
    info = client.rest("GET", "/e2e/ping")
    assert info.get("sandbox") is True, info
    assert info["database"].endswith("_e2e") or os.environ.get("E2E_ALLOW_CUSTOM_DB"), (
        f"BD del sandbox inesperada: {info['database']}. "
        "Define E2E_ALLOW_CUSTOM_DB=1 si usas E2E_DATABASE a proposito."
    )
    yield client
    if os.environ.get("E2E_DROP_SANDBOX") == "1":
        client.rest("DELETE", "/e2e/sandbox")
    client.close()


@pytest.fixture
def world(client) -> World:
    """Mundo nuevo y aislado para cada test."""
    return World.create(client)


@pytest.fixture
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.fixture
def raw_http(base_url):
    """Cliente SIN la clave del sandbox. Solo para pruebas de aislamiento de
    solo lectura (verificar que produccion rechaza cosas del sandbox)."""
    with httpx.Client(base_url=base_url, timeout=30) as http:
        assert SANDBOX_HEADER not in http.headers
        yield http
