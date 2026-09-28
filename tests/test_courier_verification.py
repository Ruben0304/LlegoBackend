"""Alta y verificación de mensajeros: validación de datos y reglas para tomar pedidos."""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from domain.orders import CourierVerificationStatus, DeliveryPerson, OrderStatus
from services.courier_verification import (
    normalize_courier_profile,
    normalize_identity_card,
    normalize_rejection_reason,
)
from services.orders_service import OrderService

ORDER_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"
OTHER_BRANCH_ID = "507f1f77bcf86cd799439099"
DELIVERY_ID = "507f1f77bcf86cd799439015"
USER_ID = "507f1f77bcf86cd799439016"


def _courier(status: CourierVerificationStatus, branches=None) -> DeliveryPerson:
    now = datetime.utcnow()
    return DeliveryPerson(
        _id=DELIVERY_ID,
        userId=USER_ID,
        name="Ana Pérez",
        verificationStatus=status,
        linkedBranchIds=branches or [],
        createdAt=now,
        updatedAt=now,
    )


# --- Validación del formulario ------------------------------------------------


def test_profile_is_normalized():
    assert normalize_courier_profile("  ana  maría ", "Pérez", "85010112345 ") == (
        "ana maría",
        "Pérez",
        "85010112345",
    )


@pytest.mark.parametrize(
    "card",
    ["", "1234567890", "123456789012", "8501011234a", "85130112345", "85013212345"],
)
def test_invalid_identity_cards_are_rejected(card):
    with pytest.raises(ValueError):
        normalize_identity_card(card)


def test_leap_day_identity_card_is_accepted():
    assert normalize_identity_card("04022912345") == "04022912345"


@pytest.mark.parametrize("name", ["", "A", "Ana3", "x" * 51])
def test_invalid_names_are_rejected(name):
    with pytest.raises(ValueError):
        normalize_courier_profile(name, "Pérez", "85010112345")


def test_rejection_reason_is_required():
    with pytest.raises(ValueError):
        normalize_rejection_reason("   ")
    assert normalize_rejection_reason(" foto  borrosa ") == "foto borrosa"


# --- Estado por defecto ----------------------------------------------------------


def test_legacy_documents_default_to_incomplete():
    dp = DeliveryPerson(
        _id=DELIVERY_ID,
        userId=USER_ID,
        name="Viejo",
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )
    assert dp.verificationStatus == CourierVerificationStatus.INCOMPLETE
    assert not dp.is_approved


# --- Aceptar pedidos -------------------------------------------------------------


def _accept(monkeypatch, courier):
    service = OrderService()
    order = SimpleNamespace(
        id=ORDER_ID,
        status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
        branchId=BRANCH_ID,
        deliveryPersonId=None,
        paymentMethod="transfer",
    )
    monkeypatch.setattr(service.orders_repo, "get_by_id", AsyncMock(return_value=order))
    monkeypatch.setattr(service.orders_repo, "set_delivery_person", AsyncMock())
    monkeypatch.setattr(
        service.delivery_repo, "get_by_user_id", AsyncMock(return_value=courier)
    )
    with pytest.raises(ValueError) as exc:
        asyncio.run(service.accept_order_for_payment(ORDER_ID, USER_ID))
    service.orders_repo.set_delivery_person.assert_not_awaited()
    return str(exc.value)


@pytest.mark.parametrize(
    "status",
    [
        CourierVerificationStatus.INCOMPLETE,
        CourierVerificationStatus.PENDING,
        CourierVerificationStatus.REJECTED,
    ],
)
def test_unapproved_courier_cannot_accept(monkeypatch, status):
    assert "verificada" in _accept(monkeypatch, _courier(status, [BRANCH_ID]))


def test_approved_courier_cannot_accept_other_branch(monkeypatch):
    courier = _courier(CourierVerificationStatus.APPROVED, [OTHER_BRANCH_ID])
    assert "sucursales asignadas" in _accept(monkeypatch, courier)


def test_approved_courier_without_branches_cannot_accept(monkeypatch):
    courier = _courier(CourierVerificationStatus.APPROVED, [])
    assert "sucursales asignadas" in _accept(monkeypatch, courier)
