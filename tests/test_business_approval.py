"""Aprobación de negocios y registro de socios.

- registerBusiness/registerMultipleBusinesses de un usuario con su solicitud
  BUSINESS aprobada crean el negocio ya aprobado; el resto sigue naciendo
  pendiente.
- approveBusiness/rejectBusiness aceptan JWT de admin/manager (Panel Admin)
  además de la clave estática ADMIN_API_KEY, que se mantiene por compatibilidad.
- Aprobar una solicitud BUSINESS aprueba los negocios pendientes del usuario
  (services/business_approval.approve_pending_businesses_of_owner).

Sin red ni Mongo: repositorios mockeados.
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest

import schema.businesses.mutations as business_mutations
import services.business_approval as business_approval
from core.config import settings
from schema.branches.inputs import BranchScheduleInput, CoordinatesInput, DayRangeInput, TimeRangeInput
from schema.branches.types import BranchTipo
from schema.businesses.inputs import (
    CreateBusinessInput,
    RegisterBranchInput,
    RegisterBusinessWithBranchesInput,
)
from utils.auth import create_access_token

OWNER_ID = "507f1f77bcf86cd799439041"
BUSINESS_ID = "507f1f77bcf86cd799439042"
PAYMENT_METHOD_ID = "507f1f77bcf86cd799439043"
ADMIN_KEY = "test-admin-key-business-approval"


def run(coro):
    return asyncio.run(coro)


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _jwt(role):
    return create_access_token({"user_id": OWNER_ID, "role": role})


def _business(status="pending", **extra):
    return SimpleNamespace(
        id=BUSINESS_ID,
        name="Cafetería Ana",
        ownerId=OWNER_ID,
        globalRating=0.0,
        avatar="",
        description=None,
        tags=[],
        isActive=status == "approved",
        approvalStatus=status,
        rejectionReason=None,
        approvedAt=None,
        rejectedAt=None,
        createdAt=datetime(2026, 10, 1),
        predefinedDeliveryFee=None,
        **extra,
    )


@pytest.fixture(autouse=True)
def secrets_config(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-business-approval")
    monkeypatch.setattr(settings, "admin_api_key", ADMIN_KEY)


# ------------------------------------------------------------ registerBusiness


@pytest.fixture
def registry(monkeypatch):
    """Repos que toca registerBusiness; guarda el negocio que se crea."""
    created = []

    async def _create(business):
        created.append(business)
        return business

    monkeypatch.setattr(business_mutations.businesses_repo, "create", AsyncMock(side_effect=_create))
    monkeypatch.setattr(business_mutations.users_repo, "add_business_id", AsyncMock())
    monkeypatch.setattr(business_mutations.branches_repo, "create", AsyncMock(side_effect=lambda b: b))
    import repositories

    monkeypatch.setattr(
        repositories.payment_methods_repo,
        "get_by_ids",
        AsyncMock(return_value=[SimpleNamespace(id=PAYMENT_METHOD_ID)]),
    )
    approved = AsyncMock(return_value=False)
    monkeypatch.setattr(business_mutations, "is_merchant_approved", approved)
    return SimpleNamespace(created=created, merchant_approved=approved)


def _branch_input():
    return RegisterBranchInput(
        name="Sucursal Vedado",
        coordinates=CoordinatesInput(lat=23.13, lng=-82.38),
        phone="+5355555555",
        schedule=BranchScheduleInput(
            ranges=[DayRangeInput(fromDay=0, toDay=6, hours=[TimeRangeInput(open="09:00", close="18:00")])]
        ),
        tipos=[BranchTipo.RESTAURANTE],
        paymentMethodIds=[PAYMENT_METHOD_ID],
    )


def _register(token):
    return run(
        business_mutations.BusinessMutation().register_business(
            info=_info(),
            business_input=CreateBusinessInput(name="Cafetería Ana"),
            branches_input=[_branch_input()],
            jwt=token,
        )
    )


def test_register_business_without_approved_request_stays_pending(registry):
    result = _register(_jwt("customer"))
    business = registry.created[0]
    assert business.approvalStatus == "pending"
    assert business.isActive is False
    assert business.approvedAt is None
    assert result.approvalStatus == "pending"
    registry.merchant_approved.assert_awaited_once_with(OWNER_ID)


def test_register_business_with_approved_request_is_born_approved(registry):
    registry.merchant_approved.return_value = True
    result = _register(_jwt("customer"))
    business = registry.created[0]
    assert business.approvalStatus == "approved"
    assert business.isActive is True
    assert business.approvedAt is not None
    assert result.approvalStatus == "approved"
    assert result.isActive is True


def test_register_multiple_businesses_follow_the_same_rule(registry):
    registry.merchant_approved.return_value = True
    results = run(
        business_mutations.BusinessMutation().register_multiple_businesses(
            info=_info(),
            businesses_input=[
                RegisterBusinessWithBranchesInput(
                    business=CreateBusinessInput(name=name), branches=[_branch_input()]
                )
                for name in ("Uno", "Dos")
            ],
            jwt=_jwt("customer"),
        )
    )
    assert [r.approvalStatus for r in results] == ["approved", "approved"]
    assert all(b.isActive for b in registry.created)


# ----------------------------------------------- approveBusiness/rejectBusiness


@pytest.fixture
def approval(monkeypatch):
    business = _business()
    monkeypatch.setattr(
        business_mutations.businesses_repo, "get_by_id", AsyncMock(return_value=business)
    )
    approve = AsyncMock(return_value=_business("approved"))
    reject = AsyncMock(return_value=_business("rejected"))
    monkeypatch.setattr(business_mutations.business_approval, "approve_business", approve)
    monkeypatch.setattr(business_mutations.business_approval, "reject_business", reject)
    return SimpleNamespace(business=business, approve=approve, reject=reject)


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_approve_and_reject_with_staff_jwt(approval, role):
    mutation = business_mutations.BusinessMutation()
    approved = run(mutation.approve_business(info=_info(), business_id=BUSINESS_ID, jwt=_jwt(role)))
    assert approved.approvalStatus == "approved"
    approval.approve.assert_awaited_once_with(BUSINESS_ID)

    rejected = run(
        mutation.reject_business(info=_info(), business_id=BUSINESS_ID, reason="Datos falsos", jwt=_jwt(role))
    )
    assert rejected.approvalStatus == "rejected"
    approval.reject.assert_awaited_once_with(BUSINESS_ID, "Datos falsos")


def test_admin_key_still_works(approval):
    mutation = business_mutations.BusinessMutation()
    run(mutation.approve_business(info=_info(), business_id=BUSINESS_ID, admin_key=ADMIN_KEY))
    run(mutation.reject_business(info=_info(), business_id=BUSINESS_ID, admin_key=ADMIN_KEY))
    approval.approve.assert_awaited_once()
    approval.reject.assert_awaited_once()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"jwt": None, "admin_key": None}, "No autorizado"),
        ({"admin_key": "otra-clave"}, "No autorizado"),
        ({"jwt": "no-es-un-jwt"}, "Invalid JWT"),
    ],
)
def test_approve_without_valid_credentials(approval, kwargs, message):
    mutation = business_mutations.BusinessMutation()
    with pytest.raises(Exception, match=message):
        run(mutation.approve_business(info=_info(), business_id=BUSINESS_ID, **kwargs))
    with pytest.raises(Exception, match=message):
        run(mutation.reject_business(info=_info(), business_id=BUSINESS_ID, **kwargs))
    approval.approve.assert_not_awaited()
    approval.reject.assert_not_awaited()


@pytest.mark.parametrize("role", ["customer", "risk_admin"])
def test_approve_rejects_other_roles_even_with_admin_key(approval, role):
    """Si llega un JWT manda el JWT: un cliente no se cuela con la clave."""
    mutation = business_mutations.BusinessMutation()
    with pytest.raises(Exception, match="Acceso denegado"):
        run(
            mutation.approve_business(
                info=_info(), business_id=BUSINESS_ID, admin_key=ADMIN_KEY, jwt=_jwt(role)
            )
        )
    approval.approve.assert_not_awaited()


def test_approve_already_approved_business(approval):
    approval.business.approvalStatus = "approved"
    with pytest.raises(Exception, match="ya está aprobado"):
        run(
            business_mutations.BusinessMutation().approve_business(
                info=_info(), business_id=BUSINESS_ID, jwt=_jwt("admin")
            )
        )


# --------------------------------------------------- services/business_approval


@pytest.fixture
def stores(monkeypatch):
    businesses = {
        "b-pending": _business("pending", ),
        "b-approved": _business("approved"),
        "b-rejected": _business("rejected"),
    }
    for key, business in businesses.items():
        business.id = key
    updates = []

    async def _update(business_id, fields):
        updates.append((business_id, fields))
        business = businesses[business_id]
        for key, value in fields.items():
            setattr(business, key, value)
        return business

    branch = SimpleNamespace(id="br-1", isActive=False)
    branch_updates = []
    monkeypatch.setattr(
        business_approval.businesses_repo, "get_by_owner", AsyncMock(return_value=list(businesses.values()))
    )
    monkeypatch.setattr(business_approval.businesses_repo, "update", AsyncMock(side_effect=_update))
    monkeypatch.setattr(business_approval.branches_repo, "get_by_business", AsyncMock(return_value=[branch]))
    monkeypatch.setattr(
        business_approval.branches_repo,
        "update",
        AsyncMock(side_effect=lambda bid, fields: branch_updates.append((bid, fields))),
    )
    return SimpleNamespace(businesses=businesses, updates=updates, branch_updates=branch_updates)


def test_approving_a_business_request_approves_only_pending_businesses(stores):
    approved = run(business_approval.approve_pending_businesses_of_owner(OWNER_ID))
    assert [b.id for b in approved] == ["b-pending"]
    assert [u[0] for u in stores.updates] == ["b-pending"]
    fields = stores.updates[0][1]
    assert fields["approvalStatus"] == "approved"
    assert fields["isActive"] is True
    assert isinstance(fields["approvedAt"], datetime)
    # Las sucursales que un rechazo previo desactivó vuelven a estar activas.
    assert stores.branch_updates == [("br-1", {"isActive": True})]
    # Rechazar un negocio es una decisión explícita: aprobar la solicitud no la deshace.
    assert stores.businesses["b-rejected"].approvalStatus == "rejected"
