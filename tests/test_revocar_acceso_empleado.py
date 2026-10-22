"""revokeBusinessAccess: el dueño (o un admin) retira el acceso de un empleado al negocio."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import schema.invitations.mutations as mutations
from utils.auth import create_access_token

DUENO, EMPLEADO, OTRO = "a" * 24, "b" * 24, "c" * 24


@pytest.fixture
def entorno(monkeypatch):
    acceso = SimpleNamespace(id="acc1", userId=EMPLEADO, businessId="neg1", isActive=True)
    monkeypatch.setattr(mutations.business_access_repo, "get_by_id", AsyncMock(return_value=acceso))
    monkeypatch.setattr(
        mutations.businesses_repo, "get_by_id", AsyncMock(return_value=SimpleNamespace(ownerId=DUENO))
    )
    revocar = AsyncMock()
    monkeypatch.setattr(mutations.access_manager, "revoke_business_access", revocar)
    return SimpleNamespace(acceso=acceso, revocar=revocar)


def _revocar(uid, rol="customer"):
    token = create_access_token({"user_id": uid, "role": rol})
    info = SimpleNamespace(context={})
    return asyncio.run(mutations.InvitationMutation.revoke_business_access(None, info, "acc1", token))


def test_el_dueno_revoca_el_acceso(entorno):
    assert _revocar(DUENO) is True
    entorno.revocar.assert_awaited_once_with("acc1", revoked_by=DUENO)


def test_otro_usuario_no_puede(entorno):
    with pytest.raises(Exception, match="Solo el dueño"):
        _revocar(OTRO)
    entorno.revocar.assert_not_awaited()


def test_no_se_revoca_al_dueno(entorno):
    entorno.acceso.userId = DUENO
    with pytest.raises(Exception, match="del dueño"):
        _revocar(DUENO)


def test_un_acceso_ya_inactivo_no_se_vuelve_a_revocar(entorno):
    entorno.acceso.isActive = False
    assert _revocar(DUENO) is True
    entorno.revocar.assert_not_awaited()
