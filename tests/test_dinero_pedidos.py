"""Fase 1 de la auditoría (21 oct 2026): el dinero de los pedidos.

- El pago cobra lo mismo que muestra el pedido (con cargo de servicio y descuentos).
- Métodos de pago inventados y precios negativos se rechazan.
- Sin zona de reparto, la distancia tiene tope; el envío que fija el negocio también.
- createOrder con la misma idempotencyKey no crea dos pedidos.
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
from pymongo.errors import DuplicateKeyError

import schema.orders.mutations as order_mutations
import services.orders_utils as orders_utils
from services.orders_service import order_service
from services.payments_service import payment_service


def test_el_pago_incluye_cargo_de_servicio_y_descuentos():
    pedido = {
        "subtotal": 1000.0,
        "deliveryFee": 200.0,
        "serviceCharge": 100.0,
        "discounts": [{"amount": 50.0}],
    }
    metodo = {"currency": "CUP", "commissionPercent": 0, "method": "transfer"}
    subtotal, envio, comision, total, moneda = payment_service._calculate_amounts(pedido, metodo)
    assert (subtotal, envio, comision, total, moneda) == (1000.0, 200.0, 0.0, 1250.0, "local")


def test_metodo_de_pago_inventado():
    with patch("services.orders_service.payment_methods_repo") as repo:
        repo.get_by_code = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Método de pago no válido"):
            asyncio.run(order_service._resolve_payment_method("bitcoin"))
        codigo, _, _ = asyncio.run(order_service._resolve_payment_method("cash"))
        assert codigo == "cash"


def test_sin_zona_no_se_reparte_a_cualquier_distancia():
    class SinZonas:
        delivery_zones = SimpleNamespace(find_one=AsyncMock(return_value=None))

    with patch.object(orders_utils, "get_database", return_value=SinZonas()):
        habana = (-82.3666, 23.1136)
        mexico = (-99.1332, 19.4326)
        with pytest.raises(ValueError, match="fuera de la zona"):
            asyncio.run(orders_utils.calculate_delivery_fee_h3(habana, mexico))
        fee, zona = asyncio.run(orders_utils.calculate_delivery_fee_h3(habana, (-82.38, 23.13)))
        assert fee > 0 and zona is None


def test_misma_clave_devuelve_el_mismo_pedido(monkeypatch):
    guardado = {}

    class Claves:
        async def insert_one(self, doc):
            if doc["_id"] in guardado:
                raise DuplicateKeyError("dup")
            guardado[doc["_id"]] = dict(doc)

        async def find_one(self, filtro):
            return guardado.get(filtro["_id"])

        async def update_one(self, filtro, cambio):
            guardado[filtro["_id"]].update(cambio["$set"])

        async def delete_one(self, filtro):
            guardado.pop(filtro["_id"], None)

    pedido = SimpleNamespace(id="ped1")
    monkeypatch.setattr(order_mutations, "_claves_pedido", lambda: Claves())
    monkeypatch.setattr(order_mutations, "orders_repo", SimpleNamespace(get_by_id=AsyncMock(return_value=pedido)))

    clave, existente = asyncio.run(order_mutations._reclamar_clave_pedido("u1", "k-123"))
    assert existente is None
    # Un reintento mientras el primero no ha terminado no crea otro pedido
    with pytest.raises(Exception, match="se está procesando"):
        asyncio.run(order_mutations._reclamar_clave_pedido("u1", "k-123"))
    guardado[clave]["orderId"] = "ped1"
    clave2, existente = asyncio.run(order_mutations._reclamar_clave_pedido("u1", "k-123"))
    assert clave2 is None and existente is pedido
    # Otra persona con la misma clave no choca
    assert asyncio.run(order_mutations._reclamar_clave_pedido("u2", "k-123"))[1] is None
