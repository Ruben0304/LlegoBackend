"""Tests de la confirmación automática de transferencias por Atajos (SMS de Transfermóvil).

El teléfono del perfil es texto libre y nadie lo verifica, así que coincidir por teléfono
no basta: se exige moneda CUP, monto suficiente, transferencia posterior al pedido,
teléfono no compartido con otra cuenta y activación atómica de la transferencia.

Sin MongoDB: repos y servicios mockeados.
"""

import asyncio
import os
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
from bson import ObjectId

import services.payments_service as payments_module
from domain.payments import PaymentAttempt, PaymentAttemptStatus
from domain.shortcut_transfer import ShortcutTransfer
from repositories.shortcut_transfer_repository import build_pending_transfers_query
from services.payments_service import PaymentService
from services.shortcut_transfer_service import transfers_covering_amount
from utils.phone import cuban_national_number, cuban_phone_regex, cuban_phone_variants

CUSTOMER_ID = str(ObjectId())
ORDER_CREATED_AT = datetime(2026, 9, 30, 12, 0, 0)


def make_transfer(amount, *, phone="55555555", minutes_after_order=5, transfer_id=None):
    return ShortcutTransfer(
        _id=str(ObjectId()),
        transfer_id=transfer_id or f"TM{ObjectId()}",
        amount=amount,
        phone=phone,
        created_at=ORDER_CREATED_AT + timedelta(minutes=minutes_after_order),
    )


def make_attempt(total=1500.0, currency="local", sends_sms=True):
    return PaymentAttempt(
        _id=str(ObjectId()),
        orderId=str(ObjectId()),
        paymentMethodId=str(ObjectId()),
        subtotal=total,
        deliveryFee=0.0,
        commissionAmount=0.0,
        totalAmount=total,
        currency=currency,
        status=PaymentAttemptStatus.AWAITING_PROOF,
        sendsSmsNotification=sends_sms,
    )


@pytest.fixture
def setup(monkeypatch):
    """Devuelve una función que arma el servicio con los mocks del escenario."""

    def _setup(
        *,
        attempt=None,
        transfers=(),
        user_phone="+5355555555",
        phone_shared=False,
        activate_results=None,
    ):
        attempt = attempt or make_attempt()
        service = PaymentService()
        service.payment_attempts_repo = SimpleNamespace(
            get_by_id=AsyncMock(return_value=attempt),
            update_status=AsyncMock(return_value=attempt),
        )
        service._get_order = AsyncMock(
            return_value={"_id": attempt.orderId, "customerId": CUSTOMER_ID, "createdAt": ORDER_CREATED_AT}
        )
        service._get_user = AsyncMock(return_value={"_id": CUSTOMER_ID, "phone": user_phone})
        service._complete_order_payment = AsyncMock()

        find = AsyncMock(return_value=list(transfers))
        activate = AsyncMock(
            side_effect=activate_results
            if activate_results is not None
            else (lambda transfer_id: SimpleNamespace(id=transfer_id))
        )
        shared = AsyncMock(return_value=phone_shared)
        monkeypatch.setattr(payments_module.shortcut_transfer_service, "find_pending_transfer", find)
        monkeypatch.setattr(payments_module.shortcut_transfer_service, "activate_transfer", activate)
        monkeypatch.setattr(payments_module.users_repo, "phone_used_by_other_user", shared)
        return SimpleNamespace(
            service=service, attempt=attempt, find=find, activate=activate, shared=shared
        )

    return _setup


def confirm(env, transfer_id=None):
    return asyncio.run(
        env.service.confirm_transfer_by_shortcut(
            payment_attempt_id=str(env.attempt.id),
            user_id=CUSTOMER_ID,
            transfer_id=transfer_id,
        )
    )


# ---------------------------------------------------------------------------
# utils.phone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["55555555", "5555 5555", "5555-5555", "5355555555", "+5355555555", "+53 5555 5555",
     "0053 5555 5555", "055555555", " (+53) 5555.5555 "],
)
def test_cuban_national_number_accepts_common_formats(raw):
    assert cuban_national_number(raw) == "55555555"


@pytest.mark.parametrize("raw", [None, "", "5555555", "555555555", "+13055551234", "+1 5555 5555", "abc"])
def test_cuban_national_number_rejects_non_cuban(raw):
    assert cuban_national_number(raw) is None


def test_cuban_phone_variants():
    assert cuban_phone_variants("+53 5555 5555") == ["55555555", "5355555555", "+5355555555"]
    assert cuban_phone_variants("+13055551234") == []


@pytest.mark.parametrize(
    "stored",
    ["55555555", "+5355555555", "+53 5555 5555", "53 5555-5555", "0053 5555 5555", "(5555) 5555"],
)
def test_cuban_phone_regex_matches_stored_formats(stored):
    assert re.match(cuban_phone_regex("5555 5555"), stored)


@pytest.mark.parametrize("stored", ["55555556", "+5355555556", "155555555", "5555555"])
def test_cuban_phone_regex_rejects_other_numbers(stored):
    assert not re.match(cuban_phone_regex("55555555"), stored)


# ---------------------------------------------------------------------------
# Query y selección de transferencias
# ---------------------------------------------------------------------------


def test_pending_query_matches_phone_in_any_format():
    query = build_pending_transfers_query(phone="+53 5555 5555", created_after=ORDER_CREATED_AT)
    assert query["activated"] is False
    assert query["created_at"] == {"$gte": ORDER_CREATED_AT}
    assert {"phone_national": "55555555"} in query["$or"]
    assert {"phone": {"$in": ["55555555", "5355555555", "+5355555555"]}} in query["$or"]


def test_pending_query_foreign_phone_is_exact():
    query = build_pending_transfers_query(phone=" +13055551234 ")
    assert query["phone"] == "+13055551234"
    assert "$or" not in query


def test_transfers_covering_amount_never_accepts_less():
    assert transfers_covering_amount([make_transfer(1499.0)], 1500.0) == []


def test_transfers_covering_amount_prefers_closest_then_newest():
    big = make_transfer(3000.0, minutes_after_order=1)
    exact_old = make_transfer(1500.0, minutes_after_order=2)
    exact_new = make_transfer(1500.0, minutes_after_order=3)
    rounding = make_transfer(1499.995, minutes_after_order=4)
    ordered = transfers_covering_amount([big, exact_old, exact_new, rounding], 1500.0)
    assert ordered == [rounding, exact_new, exact_old, big]


# ---------------------------------------------------------------------------
# confirm_transfer_by_shortcut
# ---------------------------------------------------------------------------


def test_confirms_with_matching_phone_and_amount(setup):
    transfer = make_transfer(1500.0)
    env = setup(transfers=[transfer])

    confirm(env)

    env.find.assert_awaited_once_with(phone="+5355555555", created_after=ORDER_CREATED_AT)
    env.activate.assert_awaited_once_with(transfer.id)
    args, kwargs = env.service.payment_attempts_repo.update_status.await_args
    assert args[1] == PaymentAttemptStatus.COMPLETED
    assert kwargs["shortcutTransferId"] == transfer.id
    env.service._complete_order_payment.assert_awaited_once()


def test_rejects_transfer_for_less_than_total(setup):
    env = setup(transfers=[make_transfer(10.0)])

    with pytest.raises(ValueError, match="monto menor"):
        confirm(env)

    env.activate.assert_not_awaited()
    env.service.payment_attempts_repo.update_status.assert_not_awaited()


def test_rejects_usd_attempts(setup):
    env = setup(attempt=make_attempt(total=10.0, currency="usd"), transfers=[make_transfer(10.0)])

    with pytest.raises(ValueError, match="CUP"):
        confirm(env)

    env.find.assert_not_awaited()
    env.activate.assert_not_awaited()


def test_rejects_phone_shared_with_another_account(setup):
    env = setup(transfers=[make_transfer(1500.0)], phone_shared=True)

    with pytest.raises(ValueError, match="otra cuenta"):
        confirm(env)

    env.shared.assert_awaited_once_with("+5355555555", exclude_user_id=CUSTOMER_ID)
    env.activate.assert_not_awaited()


def test_uses_next_candidate_when_first_was_claimed_concurrently(setup):
    first = make_transfer(1500.0, minutes_after_order=3)
    second = make_transfer(1500.0, minutes_after_order=2)
    env = setup(transfers=[first, second], activate_results=[None, SimpleNamespace(id=second.id)])

    confirm(env)

    assert env.activate.await_count == 2
    assert env.service.payment_attempts_repo.update_status.await_args.kwargs["shortcutTransferId"] == second.id


def test_fails_when_every_candidate_was_already_claimed(setup):
    env = setup(transfers=[make_transfer(1500.0)], activate_results=[None])

    with pytest.raises(ValueError, match="ya fue usada"):
        confirm(env)

    env.service.payment_attempts_repo.update_status.assert_not_awaited()


def test_transfer_id_path_checks_amount_but_not_profile_phone(setup):
    env = setup(transfers=[make_transfer(1500.0, transfer_id="TM123")], user_phone=None)

    confirm(env, transfer_id=" TM123 ")

    env.find.assert_awaited_once_with(transfer_id="TM123", created_after=ORDER_CREATED_AT)
    env.shared.assert_not_awaited()
    env.activate.assert_awaited_once()


def test_phone_path_without_matches_keeps_phone_not_found_error(setup):
    env = setup(transfers=[])

    with pytest.raises(ValueError, match="phone_not_found"):
        confirm(env)


def test_phone_path_requires_profile_phone(setup):
    env = setup(transfers=[make_transfer(1500.0)], user_phone="")

    with pytest.raises(ValueError, match="no tiene número"):
        confirm(env)

    env.find.assert_not_awaited()
