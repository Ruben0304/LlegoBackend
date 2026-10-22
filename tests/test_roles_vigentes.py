"""M6: el rol privilegiado del JWT (30 días) solo vale si la base lo confirma."""
import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId

from utils import roles_vigentes
from utils.auth import create_access_token
from utils.graphql_auth import require_role

ADMIN, MANAGER, EX_ADMIN = ObjectId(), ObjectId(), ObjectId()


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return self.docs


class _Usuarios:
    def find(self, filtro, proyeccion):
        roles = filtro["role"]["$in"]
        docs = [{"_id": ADMIN, "role": "admin"}, {"_id": MANAGER, "role": "manager"}]
        return _Cursor([d for d in docs if d["role"] in roles])


@pytest.fixture
def cargados(monkeypatch):
    monkeypatch.setattr(roles_vigentes, "_vigentes", None)
    asyncio.run(roles_vigentes.refrescar({"users": _Usuarios()}))
    yield


def _info():
    return SimpleNamespace(context={})


def _token(uid, rol):
    return create_access_token({"user_id": str(uid), "role": rol})


def test_admin_vigente_pasa(cargados):
    assert require_role(_token(ADMIN, "admin"), _info(), ["admin"]) == str(ADMIN)


def test_rol_quitado_deja_de_valer_aunque_el_token_siga_vivo(cargados):
    info = _info()
    with pytest.raises(Exception, match="Acceso denegado"):
        require_role(_token(EX_ADMIN, "admin"), info, ["admin"])
    assert info.context["user_role"] == "customer"


def test_si_la_base_le_da_otro_rol_privilegiado_se_usa_ese(cargados):
    info = _info()
    require_role(_token(MANAGER, "admin"), info, ["admin", "manager"])
    assert info.context["user_role"] == "manager"
    with pytest.raises(Exception):
        require_role(_token(MANAGER, "admin"), _info(), ["admin"])


def test_roles_sin_privilegios_y_arranque_sin_lectura(monkeypatch):
    assert roles_vigentes.rol_vigente(str(EX_ADMIN), "customer") == "customer"
    monkeypatch.setattr(roles_vigentes, "_vigentes", None)
    assert roles_vigentes.rol_vigente(str(EX_ADMIN), "admin") == "admin"
