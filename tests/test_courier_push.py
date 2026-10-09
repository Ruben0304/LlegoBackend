"""Pushes a la app de choferes (AppMensajeros).

Antes el backend no tenía audiencia de chofer: AppMensajeros no recibía nada
cuando le asignaban, cancelaban o preparaban un pedido, ni cuando aparecía uno
nuevo. Estos tests fijan el enrutado por bundle (audiencia `courier`), a quién
se avisa y cuándo, y que nada de esto rompe la operación que lo dispara. Sin
red ni base de datos.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import repositories
import schema.orders.mutations as order_mutations
import schema.orders.queries as order_queries
import schema.orders.subscriptions as subscriptions
import services.courier_presence as courier_presence
import services.courier_push as courier_push
import services.orders_service as orders_module
from domain.business_types import DeviceToken
from domain.orders import (
    DeliveryAddress,
    GeoPoint,
    Order,
    OrderActor,
    OrderStatus,
    PaymentStatus,
)
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_COURIER,
    AUDIENCE_CUSTOMER,
    COURIER_IOS_BUNDLE_ID,
    _filter_audience,
    device_token_repo,
    token_audience,
)
from repositories.orders_repository import delivery_persons_repo, orders_repo
from services.orders_service import OrderService
from services.push_notification_service import push_service

OK = {"success": 1, "failed": 0, "failed_tokens": []}
COURIER_ID = str(ObjectId())
COURIER_USER_ID = str(ObjectId())
HAVANA_LNG_LAT = (-82.38, 23.13)


def run(coro):
    return asyncio.run(coro)


def make_order(status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, **extra) -> Order:
    now = datetime.utcnow()
    data = dict(
        _id=str(ObjectId()),
        orderNumber="TST-1",
        customerId=str(ObjectId()),
        branchId=str(ObjectId()),
        businessId=str(ObjectId()),
        items=[],
        subtotal=100.0,
        deliveryFee=10.0,
        serviceCharge=10.0,
        total=120.0,
        currency="CUP",
        status=status,
        deliveryAddress=DeliveryAddress(
            street="Calle 23", coordinates=GeoPoint(coordinates=list(HAVANA_LNG_LAT))
        ),
        paymentMethod="cash",
        paymentStatus=PaymentStatus.PENDING,
        deadlineAt=now + timedelta(minutes=10),
        createdAt=now,
        updatedAt=now,
        lastStatusAt=now,
    )
    data.update(extra)
    return Order(**data)


class InMemoryOrders:
    """Lo mínimo de OrderRepository que usan update_status y mark_order_paid."""

    def __init__(self, order: Order):
        self.order = order

    async def get_by_id(self, order_id):
        return self.order.model_copy(deep=True)

    async def update_status(self, order_id, status, timeline_entry, extra_set_fields=None, **_):
        data = self.order.model_dump(by_alias=True)
        data.update({"status": status.value, **(extra_set_fields or {})})
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)

    async def clear_delivery_person(self, order_id):
        data = self.order.model_dump(by_alias=True)
        data["deliveryPersonId"] = None
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)

    async def update_items(self, order_id, items, subtotal, service_charge, total, timeline_entry):
        data = self.order.model_dump(by_alias=True)
        data.update(status=OrderStatus.MODIFIED_BY_STORE.value, deliveryPersonId=None, items=[])
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)

    async def resubmit_order(self, order_id, timeline_entry, **_):
        data = self.order.model_dump(by_alias=True)
        data.update(status=OrderStatus.PENDING_ACCEPTANCE.value, deliveryPersonId=None)
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)

    async def mark_paid(self, order_id, attempt_id, from_statuses, new_status, timeline_entry, deadline_at):
        data = self.order.model_dump(by_alias=True)
        data.update(
            status=new_status.value,
            paymentStatus=PaymentStatus.COMPLETED.value,
            deadlineAt=deadline_at,
        )
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)


def _device(token, bundle_id=None, platform="IOS"):
    now = datetime.utcnow()
    return DeviceToken(
        _id=str(ObjectId()),
        token=token,
        platform=platform,
        bundleId=bundle_id,
        createdAt=now,
        updatedAt=now,
    )


def _courier(
    courier_id=COURIER_ID, user_id=COURIER_USER_ID, linked=(), location=None, active=True,
    vehicle="bicicleta",
):
    return SimpleNamespace(
        id=courier_id,
        userId=user_id,
        linkedBranchIds=list(linked),
        currentLocation=GeoPoint(coordinates=list(location)) if location else None,
        isActive=active,
        vehicleType=vehicle,
    )


# ---------------------------------------------------------------- audiencia por bundle


def test_courier_bundles_route_to_courier_audience():
    # iOS (iosApp.xcodeproj) y Android (applicationId) difieren solo en mayúsculas.
    assert token_audience(_device("a", "com.llego.AppMensajeros")) == AUDIENCE_COURIER
    assert token_audience(_device("b", "com.llego.appmensajeros", "ANDROID")) == AUDIENCE_COURIER
    assert token_audience(_device("c", "com.llego.business.LlegoBusiness")) == AUDIENCE_BUSINESS
    assert token_audience(_device("d")) == AUDIENCE_CUSTOMER


def test_courier_tokens_never_reach_customer_or_business_pushes():
    tokens = [_device("cust"), _device("courier", "com.llego.AppMensajeros")]
    assert [t.token for t in _filter_audience(tokens, AUDIENCE_CUSTOMER)] == ["cust"]
    assert [t.token for t in _filter_audience(tokens, AUDIENCE_COURIER)] == ["courier"]


# ---------------------------------------------------------------- lógica pura


def test_status_messages_for_assigned_courier():
    msg = courier_push.courier_status_message
    assert msg("7", OrderStatus.CANCELLED, OrderStatus.ACCEPTED, OrderActor.CUSTOMER)[0] == "Pedido cancelado"
    assert msg("7", OrderStatus.ACCEPTED, OrderStatus.PENDING_PAYMENT, OrderActor.SYSTEM)[0] == "Pago confirmado"
    assert msg("7", OrderStatus.PREPARING, OrderStatus.ACCEPTED, OrderActor.BUSINESS)[0] == "Pedido en preparación"
    assert "#7" in msg("7", OrderStatus.READY_FOR_PICKUP, OrderStatus.PREPARING, OrderActor.BUSINESS)[1]
    # Lo que hace el propio chofer no se le notifica.
    assert msg("7", OrderStatus.ACCEPTED, OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, OrderActor.DELIVERY) is None
    assert msg("7", OrderStatus.CANCELLED, OrderStatus.PENDING_PAYMENT, OrderActor.DELIVERY) is None
    # Aceptado en efectivo al tomarlo no es "pago confirmado".
    assert msg("7", OrderStatus.ACCEPTED, OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, OrderActor.SYSTEM) is None
    assert msg("7", OrderStatus.ON_THE_WAY, OrderStatus.READY_FOR_PICKUP, OrderActor.BUSINESS) is None


def test_courier_can_take_order_mirrors_available_orders_query():
    can = courier_push.courier_can_take_order
    branch = str(ObjectId())
    # Vinculado a sucursales: solo las suyas, esté donde esté.
    assert can([branch], None, branch, None)
    assert not can([str(ObjectId())], HAVANA_LNG_LAT, branch, HAVANA_LNG_LAT)
    # Libre: por distancia a la tienda (30 km, lo que pide la app).
    assert can([], HAVANA_LNG_LAT, branch, (-82.36, 23.11))
    assert not can([], HAVANA_LNG_LAT, branch, (-79.93, 22.40))  # Santa Clara
    # Sin posición se le avisa igual.
    assert can([], None, branch, HAVANA_LNG_LAT)


def test_scheduled_for_is_shown_in_havana_time():
    # 18:00 UTC = 14:00 en Cuba (horario de verano, UTC-4).
    assert courier_push.format_scheduled_for(datetime(2026, 10, 3, 18, 0)) == "03/10 14:00"
    assert courier_push.format_scheduled_for(None) is None


# ---------------------------------------------------------------- envío al chofer asignado


def test_assigned_courier_push_uses_courier_tokens_and_bundle():
    order = make_order(OrderStatus.CANCELLED, deliveryPersonId=COURIER_ID)
    get_tokens = AsyncMock(return_value=[
        SimpleNamespace(token="ios-1", platform="IOS"),
        SimpleNamespace(token="and-1", platform="ANDROID"),
    ])
    send = AsyncMock(return_value=OK)
    with patch.object(delivery_persons_repo, "get_by_id", AsyncMock(return_value=_courier())), \
         patch.object(device_token_repo, "get_by_user_ids", get_tokens), \
         patch.object(push_service, "send_to_all", send):
        run(courier_push.notify_status_change(
            make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID), order, OrderActor.CUSTOMER
        ))

    get_tokens.assert_awaited_once_with([COURIER_USER_ID], audience=AUDIENCE_COURIER)
    ios = next(c for c in send.await_args_list if c.kwargs["platform"] == "IOS")
    android = next(c for c in send.await_args_list if c.kwargs["platform"] == "ANDROID")
    assert ios.kwargs["bundle_id"] == COURIER_IOS_BUNDLE_ID
    assert ios.kwargs["title"] == "Pedido cancelado"
    assert ios.kwargs["data"] == {
        "type": "courier_order_update",
        "orderId": str(order.id),
        "orderNumber": order.orderNumber,
        "status": "cancelled",
    }
    assert "bundle_id" not in android.kwargs


def test_courier_actions_do_not_push_to_the_courier():
    send = AsyncMock(return_value=OK)
    with patch.object(push_service, "send_to_all", send):
        run(courier_push.notify_status_change(
            make_order(OrderStatus.READY_FOR_PICKUP, deliveryPersonId=COURIER_ID),
            make_order(OrderStatus.ON_THE_WAY, deliveryPersonId=COURIER_ID),
            OrderActor.DELIVERY,
        ))
    send.assert_not_awaited()


def test_push_failure_never_raises():
    order = make_order(OrderStatus.CANCELLED, deliveryPersonId=COURIER_ID)
    with patch.object(delivery_persons_repo, "get_by_id", AsyncMock(side_effect=RuntimeError("db"))):
        run(courier_push.notify_status_change(order, order, OrderActor.SYSTEM))


# ---------------------------------------------------------------- "nuevo pedido disponible"


@pytest.fixture
def broadcast_env(monkeypatch):
    branch = SimpleNamespace(name="Pizzería 23", isDemoStore=False)
    monkeypatch.setattr(repositories.branches_repo, "get_by_id", AsyncMock(return_value=branch))
    send = AsyncMock(return_value=2)
    monkeypatch.setattr(courier_push, "send_to_courier_users", send)
    busy = AsyncMock(return_value=set())
    monkeypatch.setattr(orders_repo, "get_delivery_person_ids_with_active_order", busy)
    return SimpleNamespace(branch=branch, send=send, busy=busy)


def _order_with_pickup(**extra):
    from domain.orders import PickupAddress

    return make_order(
        OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
        pickupAddress=PickupAddress(coordinates=GeoPoint(coordinates=list(HAVANA_LNG_LAT))),
        **extra,
    )


def test_broadcast_reaches_online_couriers_that_could_take_it(broadcast_env, monkeypatch):
    order = _order_with_pickup(scheduledFor=datetime(2026, 10, 3, 18, 0))
    near, far, linked_other, released = (str(ObjectId()) for _ in range(4))
    online = {
        near: (-82.37, 23.12),
        far: (-79.93, 22.40),
        linked_other: (-82.37, 23.12),
        released: (-82.37, 23.12),
    }
    monkeypatch.setattr(courier_presence, "fetch_online_couriers_sync", lambda: online)
    couriers = [
        _courier(near, "u-near"),
        _courier(far, "u-far"),
        _courier(linked_other, "u-linked", linked=[str(ObjectId())]),
        _courier(released, "u-released"),
    ]
    get_by_ids = AsyncMock(return_value=[c for c in couriers if c.id != released])
    monkeypatch.setattr(delivery_persons_repo, "get_by_ids", get_by_ids)

    notified = run(courier_push.broadcast_new_order(order, exclude_delivery_person_ids=[released]))

    assert notified == 1
    assert released not in get_by_ids.await_args.args[0]
    user_ids, title, body, data = broadcast_env.send.await_args.args
    assert user_ids == ["u-near"]
    assert title == "Nuevo pedido disponible"
    assert "Pizzería 23" in body and "03/10 14:00" in body
    assert data["type"] == "courier_new_order"
    assert data["orderId"] == str(order.id)


def test_broadcast_skips_couriers_already_on_a_delivery(broadcast_env, monkeypatch):
    """Quien ya tiene una entrega en curso no recibe "nuevo pedido disponible":
    la app trabaja con una entrega a la vez y avisarle mientras reparte es ruido."""
    free, busy = str(ObjectId()), str(ObjectId())
    monkeypatch.setattr(
        courier_presence,
        "fetch_online_couriers_sync",
        lambda: {free: (-82.37, 23.12), busy: (-82.37, 23.12)},
    )
    monkeypatch.setattr(
        delivery_persons_repo,
        "get_by_ids",
        AsyncMock(return_value=[_courier(free, "u-free"), _courier(busy, "u-busy")]),
    )
    broadcast_env.busy.return_value = {busy}

    assert run(courier_push.broadcast_new_order(_order_with_pickup())) == 1
    assert sorted(broadcast_env.busy.await_args.args[0]) == sorted([free, busy])
    assert broadcast_env.send.await_args.args[0] == ["u-free"]


def test_broadcast_skips_couriers_without_vehicle(broadcast_env, monkeypatch):
    """Sin vehículo vinculado no puede aceptar el pedido (acceptOrderForPayment lo
    rechaza), así que tampoco se le avisa."""
    with_vehicle, without = str(ObjectId()), str(ObjectId())
    monkeypatch.setattr(
        courier_presence,
        "fetch_online_couriers_sync",
        lambda: {with_vehicle: (-82.37, 23.12), without: (-82.37, 23.12)},
    )
    monkeypatch.setattr(
        delivery_persons_repo,
        "get_by_ids",
        AsyncMock(return_value=[
            _courier(with_vehicle, "u-con"), _courier(without, "u-sin", vehicle=None),
        ]),
    )

    assert run(courier_push.broadcast_new_order(_order_with_pickup())) == 1
    assert broadcast_env.send.await_args.args[0] == ["u-con"]


def test_busy_couriers_are_the_ones_with_an_active_order(monkeypatch):
    """Mismo criterio que get_current_delivery (myCurrentDelivery), en una consulta."""
    import repositories.orders_repository as orders_repository_module

    free, busy = ObjectId(), ObjectId()
    collection = MagicMock()
    collection.distinct = AsyncMock(return_value=[busy, None])
    monkeypatch.setattr(orders_repository_module, "get_database", lambda: {"orders": collection})

    result = run(orders_repo.get_delivery_person_ids_with_active_order([str(free), str(busy)]))

    assert result == {str(busy)}
    field, query = collection.distinct.await_args.args
    assert field == "deliveryPersonId"
    assert query["deliveryPersonId"] == {"$in": [free, busy]}
    assert set(query["status"]["$in"]) == {
        "awaiting_delivery_acceptance", "pending_payment", "accepted",
        "preparing", "ready_for_pickup", "on_the_way",
    }
    assert run(orders_repo.get_delivery_person_ids_with_active_order([])) == set()


def test_broadcast_skips_demo_store_and_pickup(broadcast_env, monkeypatch):
    fetch = MagicMock(return_value={COURIER_ID: None})
    monkeypatch.setattr(courier_presence, "fetch_online_couriers_sync", fetch)

    broadcast_env.branch.isDemoStore = True
    assert run(courier_push.broadcast_new_order(_order_with_pickup())) == 0
    broadcast_env.branch.isDemoStore = False
    assert run(courier_push.broadcast_new_order(_order_with_pickup(deliveryMode="pickup"))) == 0

    fetch.assert_not_called()
    broadcast_env.send.assert_not_awaited()


def test_broadcast_without_online_couriers_sends_nothing(broadcast_env, monkeypatch):
    monkeypatch.setattr(courier_presence, "fetch_online_couriers_sync", lambda: {})
    assert run(courier_push.broadcast_new_order(_order_with_pickup())) == 0
    broadcast_env.send.assert_not_awaited()


def test_online_couriers_are_read_from_redis_presence(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.store = {
                "presence:courier:aaa:online": "1",
                "presence:courier:aaa:loc": json.dumps({"coordinates": [-82.38, 23.13]}),
                "presence:courier:bbb:online": "1",
            }

        def scan_iter(self, match, count):
            prefix = match.split("*")[0]
            suffix = match.split("*")[1]
            return [k for k in self.store if k.startswith(prefix) and k.endswith(suffix)]

        def pipeline(self):
            outer = self

            class Pipe:
                def __init__(self):
                    self.keys = []

                def get(self, key):
                    self.keys.append(key)

                def execute(self):
                    return [outer.store.get(k) for k in self.keys]

            return Pipe()

    monkeypatch.setattr(courier_presence, "redis_client", FakeRedis())
    assert courier_presence.fetch_online_couriers_sync() == {
        "aaa": (-82.38, 23.13),
        "bbb": None,
    }
    monkeypatch.setattr(courier_presence, "redis_client", None)
    assert courier_presence.fetch_online_couriers_sync() == {}


# ---------------------------------------------------------------- integración con OrderService


@pytest.fixture
def service(monkeypatch):
    svc = OrderService()
    svc._send_order_status_notification = AsyncMock()
    svc._send_order_status_update_to_business = AsyncMock()
    monkeypatch.setattr(subscriptions, "publish_branch_order", AsyncMock())
    monkeypatch.setattr(subscriptions, "publish_branch_order_update", AsyncMock())
    monkeypatch.setattr(subscriptions, "publish_order_tracking", AsyncMock())
    monkeypatch.setattr(
        orders_module.payment_attempts_repo, "get_by_order_id", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        orders_module.payment_attempts_repo, "cancel_open_attempts_for_order", AsyncMock(return_value=None)
    )
    svc.delivery_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=None), complete_delivery=AsyncMock()
    )
    return svc


def test_update_status_notifies_assigned_courier(service, monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(courier_push, "notify_assigned_courier", notify)
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID))

    run(service.update_status(
        str(service.orders_repo.order.id), OrderStatus.PREPARING, OrderActor.BUSINESS
    ))

    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "Pedido en preparación"
    assert notify.await_args.kwargs["delivery_person_id"] == COURIER_ID


def test_order_back_to_awaiting_courier_broadcasts_without_the_releasing_courier(service, monkeypatch):
    broadcast = AsyncMock(return_value=0)
    monkeypatch.setattr(courier_push, "broadcast_new_order", broadcast)
    # Lo que hace reject_order_for_payment: limpia el chofer y vuelve a esperar.
    released = make_order(OrderStatus.PENDING_PAYMENT, deliveryPersonId=COURIER_ID)

    async def scenario():
        await courier_push.notify_status_change(
            released, make_order(OrderStatus.AWAITING_DELIVERY_ACCEPTANCE), OrderActor.DELIVERY
        )
        await asyncio.sleep(0)  # deja correr la tarea en segundo plano

    run(scenario())

    broadcast.assert_awaited_once()
    assert broadcast.await_args.kwargs["exclude_delivery_person_ids"] == {COURIER_ID}


def test_courier_release_does_not_offer_the_order_back_to_that_courier(service, monkeypatch):
    """Flujo real de reject_order_for_payment: clear_delivery_person va antes de
    update_status, así que el pedido llega ya sin chofer y el que lo soltó solo
    se conoce porque se pasa aparte. Antes recibía "Nuevo pedido disponible"
    del pedido que acababa de soltar."""
    broadcast = AsyncMock(return_value=0)
    monkeypatch.setattr(courier_push, "broadcast_new_order", broadcast)
    monkeypatch.setattr(
        orders_module.payment_attempts_repo, "get_active_by_order_id", AsyncMock(return_value=None)
    )
    service.orders_repo = InMemoryOrders(
        make_order(OrderStatus.PENDING_PAYMENT, deliveryPersonId=COURIER_ID)
    )
    service.delivery_repo.get_by_user_id = AsyncMock(return_value=_courier())

    async def scenario():
        updated = await service.reject_order_for_payment(
            str(service.orders_repo.order.id), COURIER_USER_ID
        )
        await asyncio.sleep(0)  # deja correr la tarea en segundo plano
        return updated

    updated = run(scenario())

    assert updated.status == OrderStatus.AWAITING_DELIVERY_ACCEPTANCE
    assert updated.deliveryPersonId is None
    broadcast.assert_awaited_once()
    assert broadcast.await_args.kwargs["exclude_delivery_person_ids"] == {COURIER_ID}


@pytest.fixture
def unassign_env(service, monkeypatch):
    """Lo que necesitan modify_order_items y resubmit_order sin red ni BD."""
    notify = AsyncMock()
    monkeypatch.setattr(courier_push, "notify_assigned_courier", notify)
    monkeypatch.setattr(
        orders_module.payment_attempts_repo, "get_active_by_order_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        orders_module.access_checker, "check_branch_access", AsyncMock(return_value=(True, None))
    )
    monkeypatch.setattr(
        orders_module.branches_repo, "get_by_id", AsyncMock(return_value=SimpleNamespace(exchangeRate=None))
    )
    return notify


def test_store_modification_tells_the_courier_the_order_is_no_longer_his(service, unassign_env):
    """update_items quita el chofer sin pasar por update_status: antes el chofer
    seguía yendo a recoger un pedido que ya no era suyo."""
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID))

    updated = run(service.modify_order_items(
        str(service.orders_repo.order.id), [], "Sin existencias", str(ObjectId())
    ))

    assert updated.status == OrderStatus.MODIFIED_BY_STORE
    assert updated.deliveryPersonId is None
    unassign_env.assert_awaited_once()
    assert unassign_env.await_args.args[1] == "Pedido modificado por el negocio"
    assert "Ya no está asignado a ti" in unassign_env.await_args.args[2]
    assert unassign_env.await_args.kwargs["delivery_person_id"] == COURIER_ID


def test_customer_resubmission_tells_the_courier_the_order_is_no_longer_his(service, unassign_env):
    order = make_order(OrderStatus.PENDING_PAYMENT, deliveryPersonId=COURIER_ID)
    service.orders_repo = InMemoryOrders(order)

    updated = run(service.resubmit_order(str(order.id), order.customerId))

    assert updated.status == OrderStatus.PENDING_ACCEPTANCE
    unassign_env.assert_awaited_once()
    assert unassign_env.await_args.args[1] == "Pedido devuelto a la tienda"
    assert unassign_env.await_args.kwargs["delivery_person_id"] == COURIER_ID


def test_modifying_an_order_without_courier_pushes_nothing(service, unassign_env):
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.PENDING_ACCEPTANCE))

    run(service.modify_order_items(
        str(service.orders_repo.order.id), [], "Sin existencias", str(ObjectId())
    ))

    unassign_env.assert_not_awaited()


def test_unassigned_push_failure_does_not_break_the_modification(service, unassign_env, monkeypatch):
    monkeypatch.setattr(
        courier_push, "notify_courier_unassigned", AsyncMock(side_effect=RuntimeError("boom"))
    )
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID))

    updated = run(service.modify_order_items(
        str(service.orders_repo.order.id), [], "Sin existencias", str(ObjectId())
    ))
    assert updated.status == OrderStatus.MODIFIED_BY_STORE


def test_mark_order_paid_tells_courier_payment_arrived(service, monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(courier_push, "notify_assigned_courier", notify)
    service.orders_repo = InMemoryOrders(
        make_order(OrderStatus.PENDING_PAYMENT, deliveryPersonId=COURIER_ID, paymentMethod="transfer")
    )

    run(service.mark_order_paid(str(service.orders_repo.order.id), str(ObjectId())))

    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "Pago confirmado"


def test_courier_push_failure_does_not_break_status_change(service, monkeypatch):
    monkeypatch.setattr(
        courier_push, "notify_status_change", AsyncMock(side_effect=RuntimeError("boom"))
    )
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID))

    updated = run(service.update_status(
        str(service.orders_repo.order.id), OrderStatus.PREPARING, OrderActor.BUSINESS
    ))
    assert updated.status == OrderStatus.PREPARING


# ---------------------------------------------------------------- resolvers


def test_admin_assignment_pushes_to_courier(monkeypatch):
    order = make_order(OrderStatus.READY_FOR_PICKUP, deliveryPersonId=COURIER_ID)
    monkeypatch.setattr(order_mutations, "require_role", lambda jwt, info, roles: "admin-1")
    monkeypatch.setattr(order_mutations.orders_repo, "assign_delivery_person", AsyncMock(return_value=order))
    monkeypatch.setattr(order_mutations.delivery_persons_repo, "assign_order", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(courier_push, "notify_assigned_courier", notify)

    from schema.orders.inputs import AssignDeliveryPersonInput

    run(order_mutations.OrderMutation().assign_delivery_person(
        info=None,
        input=AssignDeliveryPersonInput(orderId=str(order.id), deliveryPersonId=COURIER_ID),
        jwt="token",
    ))

    notify.assert_awaited_once()
    assert notify.await_args.args[1] == "Nuevo pedido asignado"


def test_available_orders_poll_marks_courier_online(monkeypatch):
    courier = SimpleNamespace(id=COURIER_ID, linkedBranchIds=[])
    current = make_order(OrderStatus.ACCEPTED, deliveryPersonId=COURIER_ID)
    monkeypatch.setattr(order_queries, "require_auth", lambda jwt, info: COURIER_USER_ID)
    monkeypatch.setattr(order_queries, "_require_courier", AsyncMock(return_value=courier))
    monkeypatch.setattr(
        order_queries.orders_repo, "get_awaiting_delivery_acceptance_nearby", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(order_queries.orders_repo, "get_current_delivery", AsyncMock(return_value=current))
    monkeypatch.setattr(order_queries, "order_to_type", lambda o: o)
    presence = MagicMock()
    monkeypatch.setattr(order_mutations, "_redis_set_courier_presence", presence)

    result = run(order_queries.OrderQuery().available_orders_for_delivery(
        info=None, latitude=23.13, longitude=-82.38, jwt="token", radiusKm=30
    ))

    assert result == [current]
    presence.assert_called_once_with(
        COURIER_ID, online=True, longitude=-82.38, latitude=23.13, order_id=str(current.id)
    )


@pytest.fixture
def poll_env(monkeypatch):
    courier = SimpleNamespace(id=COURIER_ID, linkedBranchIds=[])
    monkeypatch.setattr(order_queries, "require_auth", lambda jwt, info: COURIER_USER_ID)
    monkeypatch.setattr(order_queries, "_require_courier", AsyncMock(return_value=courier))
    nearby = AsyncMock(return_value=[])
    monkeypatch.setattr(order_queries.orders_repo, "get_awaiting_delivery_acceptance_nearby", nearby)
    monkeypatch.setattr(order_queries.orders_repo, "get_current_delivery", AsyncMock(return_value=None))
    monkeypatch.setattr(order_queries, "order_to_type", lambda o: o)
    presence = MagicMock()
    monkeypatch.setattr(order_mutations, "_redis_set_courier_presence", presence)
    return SimpleNamespace(nearby=nearby, presence=presence)


@pytest.mark.parametrize(
    "position",
    [
        {},  # versión nueva de AppMensajeros sin GPS: no manda posición
        {"latitude": 19.4326, "longitude": -99.1332},  # versiones publicadas: Ciudad de México
    ],
)
def test_poll_without_a_real_position_marks_online_without_location(poll_env, position):
    """Antes el sondeo sin GPS dejaba al chofer en Ciudad de México en el mapa de
    Panel Admin (la posición por defecto de la app acababa en la presencia)."""
    result = run(order_queries.OrderQuery().available_orders_for_delivery(
        info=None, jwt="token", radiusKm=30, **position
    ))

    assert result == []
    poll_env.nearby.assert_not_awaited()
    poll_env.presence.assert_called_once_with(
        COURIER_ID, online=True, longitude=None, latitude=None, order_id=None
    )


def test_poll_with_gps_searches_nearby_and_records_the_position(poll_env):
    run(order_queries.OrderQuery().available_orders_for_delivery(
        info=None, jwt="token", latitude=23.13, longitude=-82.38, radiusKm=30
    ))

    poll_env.nearby.assert_awaited_once_with(-82.38, 23.13, 30)
    assert poll_env.presence.call_args.kwargs["latitude"] == 23.13
    assert poll_env.presence.call_args.kwargs["longitude"] == -82.38


def test_available_orders_position_is_optional_in_the_schema():
    from main import schema

    sdl = schema.as_str()
    line = next(l for l in sdl.splitlines() if "availableOrdersForDelivery(" in l)
    assert "latitude: Float = null" in line and "longitude: Float = null" in line
