"""Webhooks de QvaPay y TronDealer: un pago de menos no completa el pedido.

Antes ninguno comparaba lo recibido con lo esperado (context.md §12.4): un pago
de menos confirmaba el pedido y generaba el payout por lo que llegara. Ahora la
factura/wallet queda UNDERPAID, el pedido no se marca pagado, no hay payout y
el pedido queda con requiresAttention.

Sin red ni Mongo: repos, get_database y el marcado del pedido estan mockeados.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
from bson import ObjectId

import services.payments.qvapay_service as qvapay_module
import services.payments.trondealer_service as trondealer_module
from core.config import settings
from domain.crypto_payments import (
    QvaPayInvoice,
    QvaPayInvoiceStatus,
    TronDealerWallet,
    TronDealerWalletStatus,
)
from domain.orders import OrderStatus
from repositories import orders_repo
from services.payments import webhook_amounts
from services.payments.qvapay_service import QvaPayService, QvaPayWebhookPayload
from services.payments.trondealer_service import (
    TronDealerService,
    TronDealerWebhookPayload,
)
from services.payments.webhook_amounts import is_underpaid, parse_amount

ORDER_ID = ObjectId()


# ------------------------------------------------------------------ logica pura


@pytest.mark.parametrize(
    "raw,expected",
    [("10.50", 10.5), ("1", 1.0), (" 3.2 ", 3.2), ("abc", None), ("nan", None),
     ("inf", None), (None, None), ("", None)],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "received,expected,underpaid",
    [
        (25.00, 25.00, False),
        (24.99, 25.00, False),  # tolerancia de redondeo (1 centavo)
        (24.98, 25.00, True),
        (30.00, 25.00, False),  # de mas no bloquea
        (0.0, 25.00, True),
        (None, 25.00, True),  # monto ilegible
        (float("nan"), 25.00, True),
    ],
)
def test_is_underpaid(received, expected, underpaid):
    assert is_underpaid(received, expected) is underpaid


def test_flag_underpaid_order_keeps_status_and_clears_deadline():
    order = SimpleNamespace(status=OrderStatus.PENDING_PAYMENT)
    with patch.object(orders_repo, "get_by_id", AsyncMock(return_value=order)), \
         patch.object(orders_repo, "mark_requires_attention", AsyncMock(return_value=order)) as mark:
        asyncio.run(webhook_amounts.flag_underpaid_order(str(ORDER_ID), "motivo"))

    args, kwargs = mark.await_args
    assert args == (str(ORDER_ID), "motivo")
    assert kwargs["clear_deadline"] is True
    assert kwargs["timeline_entry"].status == OrderStatus.PENDING_PAYMENT


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def db():
    fake = MagicMock()
    fake.orders.find_one = AsyncMock(return_value={"status": "pending_payment"})
    fake.orders.update_one = AsyncMock()
    return fake


@pytest.fixture
def flag():
    return AsyncMock()


@pytest.fixture(autouse=True)
def no_external_checks(monkeypatch, db, flag):
    monkeypatch.setattr(settings, "qvapay_webhook_secret", "")
    monkeypatch.setattr(settings, "qvapay_platform_pin", "")
    monkeypatch.setattr(settings, "trondealer_webhook_secret", "")
    monkeypatch.setattr(settings, "trondealer_allowed_ips", "")
    monkeypatch.setattr(qvapay_module, "get_database", lambda: db)
    monkeypatch.setattr(trondealer_module, "get_database", lambda: db)
    monkeypatch.setattr(qvapay_module, "flag_underpaid_order", flag)
    monkeypatch.setattr(trondealer_module, "flag_underpaid_order", flag)


# ------------------------------------------------------------------ QvaPay


def _invoice(status=QvaPayInvoiceStatus.PENDING, amount=25.0, invoiced=None):
    return QvaPayInvoice(
        _id=ObjectId(), orderId=ORDER_ID, branchId=ObjectId(), businessId=ObjectId(),
        transactionUuid="uuid-1", remoteId=str(ORDER_ID), amount=amount,
        invoicedAmount=invoiced, description="Pedido #1", status=status,
    )


def _qvapay(invoice):
    invoices = SimpleNamespace(
        get_by_transaction_uuid=AsyncMock(return_value=invoice),
        mark_completed=AsyncMock(return_value=invoice),
        mark_underpaid=AsyncMock(return_value=invoice),
    )
    payouts = SimpleNamespace(create=AsyncMock())
    return QvaPayService(invoices_repo=invoices, payouts_repo=payouts), invoices, payouts


def _qvapay_payload(amount):
    return QvaPayWebhookPayload(
        transaction_uuid="uuid-1", remote_id=str(ORDER_ID), amount=amount,
        status="paid", signed=True, created_at="2026-10-01T00:00:00Z",
        updated_at="2026-10-01T00:00:00Z",
    )


@pytest.mark.parametrize("amount", ["25.00", "24.99", "30"])
def test_qvapay_full_payment_completes_order_and_creates_payout(db, flag, amount):
    svc, invoices, payouts = _qvapay(_invoice())

    assert asyncio.run(svc.handle_webhook(_qvapay_payload(amount), None)) is True

    invoices.mark_completed.assert_awaited_once_with("uuid-1", received_amount=float(amount))
    invoices.mark_underpaid.assert_not_awaited()
    assert db.orders.update_one.await_args.args[1]["$set"]["paymentStatus"] == "completed"
    assert payouts.create.await_args.args[0].amount == float(amount)
    flag.assert_not_awaited()


@pytest.mark.parametrize("amount,received", [("10.00", 10.0), ("24.98", 24.98), ("abc", None)])
def test_qvapay_underpayment_flags_order_without_payment_or_payout(db, flag, amount, received):
    svc, invoices, payouts = _qvapay(_invoice())

    assert asyncio.run(svc.handle_webhook(_qvapay_payload(amount), None)) is True

    invoices.mark_underpaid.assert_awaited_once_with("uuid-1", received)
    invoices.mark_completed.assert_not_awaited()
    db.orders.update_one.assert_not_awaited()
    payouts.create.assert_not_awaited()
    order_id, reason = flag.await_args.args
    assert order_id == str(ORDER_ID)
    assert "25.00" in reason and "QvaPay" in reason


def test_qvapay_compares_against_invoiced_amount_in_test_mode(db, flag):
    # Con QVAPAY_TEST_AMOUNT la factura se cobra por 1.00 aunque el pedido valga 25.
    svc, invoices, payouts = _qvapay(_invoice(amount=25.0, invoiced=1.0))

    assert asyncio.run(svc.handle_webhook(_qvapay_payload("1.00"), None)) is True

    invoices.mark_completed.assert_awaited_once()
    flag.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [QvaPayInvoiceStatus.COMPLETED, QvaPayInvoiceStatus.UNDERPAID]
)
def test_qvapay_duplicate_webhooks_are_ignored(db, flag, status):
    svc, invoices, payouts = _qvapay(_invoice(status=status))

    assert asyncio.run(svc.handle_webhook(_qvapay_payload("25.00"), None)) is False

    invoices.mark_completed.assert_not_awaited()
    invoices.mark_underpaid.assert_not_awaited()
    payouts.create.assert_not_awaited()
    flag.assert_not_awaited()


def test_qvapay_create_invoice_stores_invoiced_amount(monkeypatch):
    monkeypatch.setattr(settings, "qvapay_app_id", "app")
    monkeypatch.setattr(settings, "qvapay_app_secret", "secret")
    monkeypatch.setattr(settings, "qvapay_test_amount", 1.0)
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "app_id": "app", "amount": 1.0, "description": "d", "remote_id": str(ORDER_ID),
        "transaction_uuid": "uuid-1", "url": "https://qvapay.com/pay/uuid-1",
    }
    http = AsyncMock()
    http.post = AsyncMock(return_value=response)
    http.__aenter__.return_value = http
    svc, invoices, _ = _qvapay(None)
    invoices.create = AsyncMock()

    with patch.object(qvapay_module.httpx, "AsyncClient", return_value=http):
        asyncio.run(svc.create_invoice(
            order_id=str(ORDER_ID), branch_id=str(ObjectId()), business_id=str(ObjectId()),
            amount=25.0, description="d",
        ))

    stored = invoices.create.await_args.args[0]
    assert stored.amount == 25.0
    assert stored.invoicedAmount == 1.0


# ------------------------------------------------------------------ TronDealer


def _wallet(status=TronDealerWalletStatus.PENDING, tx_hash=None, received=None):
    return TronDealerWallet(
        _id=ObjectId(), orderId=ORDER_ID, branchId=ObjectId(), businessId=ObjectId(),
        address="TADDR", expectedAmount=25.0, status=status, txHash=tx_hash,
        receivedAmount=received,
    )


def _trondealer(wallet):
    wallets = SimpleNamespace(
        get_by_address=AsyncMock(return_value=wallet),
        mark_completed=AsyncMock(return_value=wallet),
        mark_underpaid=AsyncMock(return_value=wallet),
    )
    payouts = SimpleNamespace(create=AsyncMock())
    return TronDealerService(wallets_repo=wallets, payouts_repo=payouts), wallets, payouts


def _td_payload(amount, txhash="tx-1"):
    return TronDealerWebhookPayload(address="TADDR", amount=amount, token="USDT", txhash=txhash)


def _td_call(svc, payload):
    return asyncio.run(svc.handle_webhook(
        raw_body=b"{}", signature_header=None, client_ip=None, payload=payload
    ))


@pytest.mark.parametrize("amount", ["25.00", "24.995", "26"])
def test_trondealer_full_deposit_completes_order_and_creates_payout(db, flag, amount):
    svc, wallets, payouts = _trondealer(_wallet())

    assert _td_call(svc, _td_payload(amount)) is True

    wallets.mark_completed.assert_awaited_once()
    wallets.mark_underpaid.assert_not_awaited()
    assert db.orders.update_one.await_args.args[1]["$set"]["paymentStatus"] == "completed"
    assert payouts.create.await_args.args[0].amount == float(amount)
    flag.assert_not_awaited()


@pytest.mark.parametrize("amount,received", [("5", 5.0), ("24.90", 24.9), ("not-a-number", None)])
def test_trondealer_underpayment_flags_order_without_payment_or_payout(db, flag, amount, received):
    svc, wallets, payouts = _trondealer(_wallet())

    assert _td_call(svc, _td_payload(amount)) is True

    assert wallets.mark_underpaid.await_args.kwargs["received_amount"] == received
    wallets.mark_completed.assert_not_awaited()
    db.orders.update_one.assert_not_awaited()
    payouts.create.assert_not_awaited()
    order_id, reason = flag.await_args.args
    assert order_id == str(ORDER_ID)
    assert "25.00" in reason and "tx-1" in reason


def test_trondealer_extra_deposit_on_underpaid_wallet_is_flagged_not_paid(db, flag):
    svc, wallets, payouts = _trondealer(
        _wallet(status=TronDealerWalletStatus.UNDERPAID, tx_hash="tx-1", received=10.0)
    )

    assert _td_call(svc, _td_payload("15.00", txhash="tx-2")) is False

    wallets.mark_completed.assert_not_awaited()
    payouts.create.assert_not_awaited()
    db.orders.update_one.assert_not_awaited()
    assert "tx-2" in flag.await_args.args[1]


@pytest.mark.parametrize(
    "wallet",
    [
        _wallet(status=TronDealerWalletStatus.COMPLETED, tx_hash="tx-1", received=25.0),
        _wallet(status=TronDealerWalletStatus.UNDERPAID, tx_hash="tx-1", received=10.0),
    ],
)
def test_trondealer_duplicate_webhooks_are_ignored(db, flag, wallet):
    svc, wallets, payouts = _trondealer(wallet)

    assert _td_call(svc, _td_payload("25.00", txhash="tx-1")) is False

    wallets.mark_completed.assert_not_awaited()
    wallets.mark_underpaid.assert_not_awaited()
    payouts.create.assert_not_awaited()
    flag.assert_not_awaited()
