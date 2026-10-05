"""Un mensajero solo puede tener una entrega en curso.

accept_order_for_payment (el flujo principal de AppMensajeros) no lo comprobaba:
un chofer con un pedido en camino podía aceptar otro. accept_delivery (flujo
antiguo) ya lo exigía. Sin MongoDB: repos y servicios mockeados.
"""

import asyncio
import os
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

from domain.orders import OrderStatus
from services.orders_service import OrderService

USER_ID = str(ObjectId())
COURIER_ID = str(ObjectId())
ORDER_ID = str(ObjectId())
OTHER_ORDER_ID = str(ObjectId())


def run(coro):
    return asyncio.run(coro)


def _order(order_id=ORDER_ID, status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, delivery_person_id=None):
    return SimpleNamespace(
        id=order_id,
        status=status,
        deliveryPersonId=delivery_person_id,
        paymentMethod="cash",
    )


@pytest.fixture
def service():
    svc = OrderService()
    courier = SimpleNamespace(id=COURIER_ID, vehicleType="bicicleta")
    svc._require_delivery_person = AsyncMock(return_value=courier)
    svc.orders_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=_order()),
        get_current_delivery=AsyncMock(return_value=None),
        set_delivery_person=AsyncMock(return_value=_order(delivery_person_id=COURIER_ID)),
    )
    svc.delivery_repo = SimpleNamespace(assign_order=AsyncMock())
    svc._is_cash_payment_method = AsyncMock(return_value=True)
    svc.update_status = AsyncMock(
        return_value=_order(status=OrderStatus.ACCEPTED, delivery_person_id=COURIER_ID)
    )
    return svc


def test_courier_with_active_delivery_cannot_accept_another(service):
    service.orders_repo.get_current_delivery.return_value = _order(
        order_id=OTHER_ORDER_ID, status=OrderStatus.ON_THE_WAY, delivery_person_id=COURIER_ID
    )

    with pytest.raises(ValueError, match="Ya tienes un pedido en curso"):
        run(service.accept_order_for_payment(ORDER_ID, USER_ID))

    service.orders_repo.get_current_delivery.assert_awaited_once_with(COURIER_ID)
    service.orders_repo.set_delivery_person.assert_not_awaited()
    service.delivery_repo.assign_order.assert_not_awaited()
    service.update_status.assert_not_awaited()


def test_courier_without_active_delivery_accepts(service):
    result = run(service.accept_order_for_payment(ORDER_ID, USER_ID))

    assert result.status == OrderStatus.ACCEPTED
    service.orders_repo.set_delivery_person.assert_awaited_once_with(ORDER_ID, COURIER_ID)
    service.delivery_repo.assign_order.assert_awaited_once_with(COURIER_ID, ORDER_ID)


def test_retry_of_an_already_accepted_order_stays_idempotent(service):
    """Si la respuesta se perdió y el chofer reintenta, no se le bloquea con su propio pedido."""
    mine = _order(status=OrderStatus.ACCEPTED, delivery_person_id=COURIER_ID)
    service.orders_repo.get_by_id.return_value = mine
    service.orders_repo.get_current_delivery.return_value = mine

    result = run(service.accept_order_for_payment(ORDER_ID, USER_ID))

    assert result is mine
    service.orders_repo.set_delivery_person.assert_not_awaited()
