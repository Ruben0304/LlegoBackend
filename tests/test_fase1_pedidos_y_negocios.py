"""Fase 1 de la auditoría (22 oct 2026): recogida en tienda, alta de negocios, imágenes,
webhooks y cobro en efectivo.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

import pytest

import schema.businesses.mutations as business_mutations
import services.orders_service as orders_service_mod
from core.config import settings
from domain.orders import ALLOWED_TRANSITIONS, OrderStatus
from services.payments_service import payment_service
from utils.s3 import clave_en_carpeta

USER_ID = "507f1f77bcf86cd799439011"


# ---------------------------------------------------------------- recogida en tienda


def _pedido(**kw):
    base = dict(
        status=OrderStatus.READY_FOR_PICKUP,
        deliveryMode="pickup",
        branchId="b1",
        deliveryVerificationCode="4821",
        paymentMethod="cash",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_recogida_puede_pasar_a_entregado():
    assert OrderStatus.DELIVERED.value in ALLOWED_TRANSITIONS[OrderStatus.READY_FOR_PICKUP.value]


def test_la_tienda_entrega_la_recogida_con_el_codigo(monkeypatch):
    servicio = orders_service_mod.order_service
    repo = SimpleNamespace(get_by_id=AsyncMock(return_value=_pedido()), update_payment_status=AsyncMock())
    monkeypatch.setattr(servicio, "orders_repo", repo)
    monkeypatch.setattr(servicio, "_check_delivery_code", AsyncMock())
    monkeypatch.setattr(servicio, "_is_cash_payment_method", AsyncMock(return_value=True))
    monkeypatch.setattr(servicio, "update_status", AsyncMock(return_value="entregado"))
    acceso = SimpleNamespace(require_branch_access=AsyncMock())
    monkeypatch.setattr(orders_service_mod, "access_checker", acceso)

    assert asyncio.run(servicio.deliver_pickup_order("p1", USER_ID, "4821")) == "entregado"
    acceso.require_branch_access.assert_awaited_once_with(USER_ID, "b1")
    assert servicio.update_status.await_args.args[1] == OrderStatus.DELIVERED
    repo.update_payment_status.assert_awaited_once()


@pytest.mark.parametrize(
    "cambios, mensaje",
    [({"deliveryMode": "app"}, "no es de recogida"), ({"status": OrderStatus.PREPARING}, "no está listo")],
)
def test_recogida_rechaza_pedidos_que_no_tocan(monkeypatch, cambios, mensaje):
    servicio = orders_service_mod.order_service
    monkeypatch.setattr(servicio, "orders_repo", SimpleNamespace(get_by_id=AsyncMock(return_value=_pedido(**cambios))))
    with pytest.raises(ValueError, match=mensaje):
        asyncio.run(servicio.deliver_pickup_order("p1", USER_ID, "4821"))


# ---------------------------------------------------------------- imágenes


def test_clave_en_carpeta():
    assert clave_en_carpeta(f"users/avatars/{USER_ID}_1700.jpg", "users/avatars", USER_ID)
    assert not clave_en_carpeta(f"users/avatars/otro_1700.jpg", "users/avatars", USER_ID)
    assert not clave_en_carpeta("products/abc_1700.png", "users/avatars", USER_ID)
    assert not clave_en_carpeta("users/avatars/../products/x.png", "users/avatars")
    assert not clave_en_carpeta("https://evil/x.png", "branches/avatars")
    assert clave_en_carpeta("branches/covers/abc_1.jpg", "branches/covers")


# ---------------------------------------------------------------- alta de negocios


def test_moneda_y_tasa_de_la_sucursal():
    both = SimpleNamespace(acceptedCurrency=SimpleNamespace(value="BOTH"), exchangeRate=480)
    assert business_mutations._moneda_sucursal(both) == "BOTH"
    assert business_mutations._tasa_sucursal(both) == 480
    with pytest.raises(Exception, match="solo aplica"):
        business_mutations._tasa_sucursal(SimpleNamespace(acceptedCurrency=SimpleNamespace(value="CUP"), exchangeRate=480))
    assert business_mutations._moneda_sucursal(SimpleNamespace(acceptedCurrency=None, exchangeRate=None)) is None


# ---------------------------------------------------------------- webhooks


def test_webhooks_sin_secreto_se_rechazan_fuera_de_desarrollo(monkeypatch):
    from services.payments.qvapay_service import QvaPayService
    from services.payments.trondealer_service import TronDealerService

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "qvapay_webhook_secret", "")
    monkeypatch.setattr(settings, "trondealer_webhook_secret", "")
    for clase in (QvaPayService, TronDealerService):
        with pytest.raises(ValueError, match="sin secreto"):
            clase._verify_signature(object.__new__(clase), *([None] * (clase._verify_signature.__code__.co_argcount - 1)))


# ---------------------------------------------------------------- efectivo


def test_cobro_en_efectivo_acepta_el_usuario_del_chofer(monkeypatch):
    from domain.payments import PaymentAttemptStatus

    intento = SimpleNamespace(status=PaymentAttemptStatus.AWAITING_DELIVERY, orderId="o1")
    monkeypatch.setattr(payment_service, "payment_attempts_repo", SimpleNamespace(
        get_by_id=AsyncMock(return_value=intento), confirm_delivery_cash=AsyncMock(return_value=None)))
    monkeypatch.setattr(payment_service, "_get_order", AsyncMock(return_value={"deliveryPersonId": "dp1"}))
    monkeypatch.setattr(payment_service, "_process_cash_payment_completion", AsyncMock())
    monkeypatch.setattr(payment_service, "_complete_order_payment", AsyncMock())
    with patch("repositories.delivery_persons_repo") as repo:
        repo.get_by_user_id = AsyncMock(return_value=SimpleNamespace(id="dp1"))
        # Pasa la comprobación de chofer (antes fallaba siempre) y llega a confirmar
        asyncio.run(payment_service.confirm_cash_received("pa1", USER_ID))
        repo.get_by_user_id = AsyncMock(return_value=SimpleNamespace(id="otro"))
        with pytest.raises(ValueError, match="No autorizado"):
            asyncio.run(payment_service.confirm_cash_received("pa1", USER_ID))
