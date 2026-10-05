"""Mensajero sin vehículo: deliveryPerson no debe romper la query y no puede aceptar pedidos.

DeliveryPersonType.vehicleType es un enum obligatorio en GraphQL, pero
delivery_persons.vehicleType es opcional: los registros nacen sin vehículo (al aprobar
la solicitud de mensajero, los de staff, los antiguos creados al primer uso) hasta
que el mensajero llama a linkVehicle. Los resolvers hacían `dp.vehicleType.value`, que
con None lanzaba AttributeError: el cliente recibía deliveryPerson null y un error en
GetOrderDetail / GetOrderTracking.

Sin MongoDB: repos mockeados y un schema GraphQL mínimo con los resolvers reales.
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
import strawberry
from bson import ObjectId

import schema.orders.types as order_types
from domain.orders import DeliveryPerson, OrderStatus
from schema.orders.types import (
    BranchDeliveryRequestType,
    DeliveryPersonType,
    OrderType,
    VehicleTypeEnum,
    vehicle_type_for_graphql,
)
from services.orders_service import VEHICLE_REQUIRED_MESSAGE, OrderService

DP_ID = str(ObjectId())
USER_ID = str(ObjectId())
ORDER_ID = str(ObjectId())


def run(coro):
    return asyncio.run(coro)


def _resolver(type_cls):
    field = next(
        f for f in type_cls.__strawberry_definition__.fields if f.python_name == "delivery_person"
    )
    return field.base_resolver.wrapped_func


_order_delivery_person = _resolver(OrderType)
_link_request_delivery_person = _resolver(BranchDeliveryRequestType)


@strawberry.type
class _Query:
    """Expone los resolvers reales de OrderType y BranchDeliveryRequestType."""

    @strawberry.field
    async def order_delivery_person(self) -> Optional[DeliveryPersonType]:
        return await _order_delivery_person(SimpleNamespace(deliveryPersonId=DP_ID))

    @strawberry.field
    async def link_request_delivery_person(self) -> Optional[DeliveryPersonType]:
        return await _link_request_delivery_person(SimpleNamespace(deliveryPersonId=DP_ID))


_schema = strawberry.Schema(query=_Query)

QUERY = """
{
  orderDeliveryPerson { name vehicleType }
  linkRequestDeliveryPerson { name vehicleType }
}
"""


def _delivery_person(vehicle_type=None):
    now = datetime.utcnow()
    return DeliveryPerson(
        _id=DP_ID,
        userId=USER_ID,
        name="Mensajero Uno",
        phone="+5355555555",
        vehicleType=vehicle_type,
        approved=True,
        createdAt=now,
        updatedAt=now,
    )


@pytest.fixture
def repo(monkeypatch):
    get_by_id = AsyncMock()
    monkeypatch.setattr(order_types.delivery_persons_repo, "get_by_id", get_by_id)
    return get_by_id


def _execute():
    return run(_schema.execute(QUERY))


# ---------------------------------------------------------------------------
# deliveryPerson { vehicleType }
# ---------------------------------------------------------------------------


def test_courier_without_vehicle_does_not_break_delivery_person(repo):
    repo.return_value = _delivery_person(vehicle_type=None)

    result = _execute()

    assert result.errors is None
    for field in ("orderDeliveryPerson", "linkRequestDeliveryPerson"):
        assert result.data[field] == {"name": "Mensajero Uno", "vehicleType": "SIN_VEHICULO"}


def test_courier_with_vehicle_keeps_its_vehicle(repo):
    repo.return_value = _delivery_person(vehicle_type="triciclo")

    result = _execute()

    assert result.errors is None
    assert result.data["orderDeliveryPerson"]["vehicleType"] == "TRICICLO"
    assert result.data["linkRequestDeliveryPerson"]["vehicleType"] == "TRICICLO"


@pytest.mark.parametrize("raw", [None, "", "moto", "a_pie"])
def test_missing_or_retired_vehicle_maps_to_sin_vehiculo(raw):
    assert vehicle_type_for_graphql(raw) is VehicleTypeEnum.SIN_VEHICULO


# ---------------------------------------------------------------------------
# Aceptar pedidos exige vehículo
# ---------------------------------------------------------------------------


def _order(status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, delivery_person_id=None):
    return SimpleNamespace(
        id=ORDER_ID, status=status, deliveryPersonId=delivery_person_id, paymentMethod="cash"
    )


@pytest.fixture
def service():
    svc = OrderService()
    courier = SimpleNamespace(id=DP_ID, vehicleType=None, currentOrderId=None)
    svc._require_delivery_person = AsyncMock(return_value=courier)
    svc.orders_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=_order()),
        get_current_delivery=AsyncMock(return_value=None),
        set_delivery_person=AsyncMock(),
        assign_delivery_person=AsyncMock(),
    )
    svc.delivery_repo = SimpleNamespace(
        assign_order=AsyncMock(), get_by_user_id=AsyncMock(return_value=courier)
    )
    svc.update_status = AsyncMock()
    return svc


def test_courier_without_vehicle_cannot_accept_order_for_payment(service):
    with pytest.raises(ValueError, match="Vincula tu vehículo"):
        run(service.accept_order_for_payment(ORDER_ID, USER_ID))

    assert str(VEHICLE_REQUIRED_MESSAGE).startswith("Vincula tu vehículo")
    service.orders_repo.set_delivery_person.assert_not_awaited()
    service.update_status.assert_not_awaited()


def test_courier_without_vehicle_cannot_use_legacy_accept_delivery(service):
    service.orders_repo.get_by_id.return_value = _order(status=OrderStatus.READY_FOR_PICKUP)

    with pytest.raises(ValueError, match="Vincula tu vehículo"):
        run(service.accept_delivery(ORDER_ID, USER_ID))

    service.orders_repo.assign_delivery_person.assert_not_awaited()


def test_retry_of_an_order_assigned_before_the_rule_stays_idempotent(service):
    """Un pedido ya asignado (antes de exigir vehículo) no se le bloquea al reintentar."""
    mine = _order(status=OrderStatus.ACCEPTED, delivery_person_id=DP_ID)
    service.orders_repo.get_by_id.return_value = mine

    assert run(service.accept_order_for_payment(ORDER_ID, USER_ID)) is mine
