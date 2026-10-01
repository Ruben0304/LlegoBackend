"""Tiempo real para la app de negocios: newBranchOrder y branchOrderUpdated.

Antes nadie publicaba en `branch:{branchId}` ni en `branch_updates:{branchId}`
(schema/orders/subscriptions.py), así que las dos suscripciones de la app de
negocios nunca emitían. Ahora OrderService publica al crear el pedido y en cada
cambio de estado o de pago, sin romper ni frenar la operación principal.

Pubsub mockeado salvo en el test de punta a punta, que usa el pubsub en memoria
real (el mismo que en producción, ver context.md §5).
"""

import asyncio
import contextlib
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.orders.subscriptions as subscriptions
import services.orders_service as orders_module
from domain.orders import (
    DeliveryAddress,
    GeoPoint,
    Order,
    OrderStatus,
    PaymentStatus,
)
from services.orders_service import OrderService

BRANCH_ID = str(ObjectId())
USER_ID = str(ObjectId())


def make_order(status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE, **extra) -> Order:
    now = datetime.utcnow()
    data = dict(
        _id=str(ObjectId()),
        orderNumber="TST-1",
        customerId=str(ObjectId()),
        branchId=BRANCH_ID,
        businessId=str(ObjectId()),
        items=[],
        subtotal=100.0,
        deliveryFee=10.0,
        serviceCharge=10.0,
        total=120.0,
        currency="CUP",
        status=status,
        deliveryAddress=DeliveryAddress(
            street="Calle 23", coordinates=GeoPoint(coordinates=[-82.38, 23.13])
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
    """Lo mínimo de OrderRepository que usan update_status y compañía."""

    def __init__(self, order: Order):
        self.order = order

    async def get_by_id(self, order_id):
        return self.order.model_copy(deep=True)

    async def update_status(self, order_id, status, timeline_entry, extra_set_fields=None, **_):
        data = self.order.model_dump(by_alias=True)
        data.update({"status": status.value, **(extra_set_fields or {})})
        self.order = Order.model_validate(data)
        return self.order.model_copy(deep=True)

    async def extend_deadline(self, order_id, deadline_at, expected_status):
        data = self.order.model_dump(by_alias=True)
        data["deadlineAt"] = max(self.order.deadlineAt, deadline_at)
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


@pytest.fixture
def publishers(monkeypatch):
    new = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(subscriptions, "publish_branch_order", new)
    monkeypatch.setattr(subscriptions, "publish_branch_order_update", update)
    return SimpleNamespace(new=new, update=update)


@pytest.fixture
def service(monkeypatch):
    svc = OrderService()
    # Las notificaciones push no son parte de este test.
    svc._send_order_status_notification = AsyncMock()
    svc._send_order_status_update_to_business = AsyncMock()
    monkeypatch.setattr(
        orders_module.payment_attempts_repo, "get_by_order_id", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        orders_module.payment_attempts_repo,
        "cancel_open_attempts_for_order",
        AsyncMock(return_value=None),
    )
    return svc


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Qué se publica y en qué canal
# ---------------------------------------------------------------------------


def test_new_order_goes_to_new_branch_order_channel(service, publishers):
    order = make_order(OrderStatus.PENDING_ACCEPTANCE)

    run(service._publish_branch_order_event(order, is_new=True))

    publishers.new.assert_awaited_once_with(BRANCH_ID, order)
    publishers.update.assert_not_awaited()


def test_status_change_is_published_to_branch_updates(service, publishers):
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.AWAITING_DELIVERY_ACCEPTANCE))

    updated = run(
        service.update_status(
            str(service.orders_repo.order.id), OrderStatus.ACCEPTED, orders_module.OrderActor.DELIVERY
        )
    )

    publishers.update.assert_awaited_once()
    branch_id, published = publishers.update.await_args.args
    assert branch_id == BRANCH_ID
    assert published.status == OrderStatus.ACCEPTED
    assert published.deadlineAt == updated.deadlineAt
    publishers.new.assert_not_awaited()


def test_resubmitted_order_is_also_announced_as_new(service, publishers):
    """Vuelve a PENDING_ACCEPTANCE: la tienda tiene que responder otra vez."""
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.AWAITING_DELIVERY_ACCEPTANCE))

    run(
        service.update_status(
            str(service.orders_repo.order.id),
            OrderStatus.PENDING_ACCEPTANCE,
            orders_module.OrderActor.CUSTOMER,
        )
    )

    publishers.update.assert_awaited_once()
    publishers.new.assert_awaited_once()
    assert publishers.new.await_args.args[1].status == OrderStatus.PENDING_ACCEPTANCE


def test_cancellation_is_published(service, publishers):
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.PENDING_ACCEPTANCE))

    run(
        service.update_status(
            str(service.orders_repo.order.id), OrderStatus.CANCELLED, orders_module.OrderActor.CUSTOMER
        )
    )

    assert publishers.update.await_args.args[1].status == OrderStatus.CANCELLED


def test_payment_confirmation_is_published(service, publishers):
    service.orders_repo = InMemoryOrders(
        make_order(OrderStatus.PAYMENT_IN_PROGRESS, paymentMethod="transfer")
    )

    run(service.mark_order_paid(str(service.orders_repo.order.id), str(ObjectId())))

    published = publishers.update.await_args.args[1]
    assert published.status == OrderStatus.ACCEPTED
    assert published.paymentStatus == PaymentStatus.COMPLETED


def test_customer_starting_payment_is_published(service, publishers):
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.PENDING_PAYMENT))

    run(service.extend_payment_deadline(str(service.orders_repo.order.id)))

    published = publishers.update.await_args.args[1]
    assert published.deadlineAt > datetime.utcnow() + timedelta(minutes=14)


def test_external_writers_publish_by_order_id(service, publishers):
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.ACCEPTED))

    run(service.publish_branch_order_changed(str(service.orders_repo.order.id)))

    publishers.update.assert_awaited_once()


# ---------------------------------------------------------------------------
# Publicar nunca rompe la operación principal
# ---------------------------------------------------------------------------


def test_publish_failure_does_not_break_status_change(service, monkeypatch):
    monkeypatch.setattr(
        subscriptions, "publish_branch_order_update", AsyncMock(side_effect=RuntimeError("boom"))
    )
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.AWAITING_DELIVERY_ACCEPTANCE))

    updated = run(
        service.update_status(
            str(service.orders_repo.order.id), OrderStatus.ACCEPTED, orders_module.OrderActor.DELIVERY
        )
    )

    assert updated.status == OrderStatus.ACCEPTED
    # El resto del aviso (push al cliente y al negocio) sigue saliendo.
    service._send_order_status_notification.assert_awaited_once()
    service._send_order_status_update_to_business.assert_awaited_once()


def test_external_writer_publish_never_raises(service, publishers):
    service.orders_repo = SimpleNamespace(get_by_id=AsyncMock(side_effect=RuntimeError("db caida")))

    run(service.publish_branch_order_changed(str(ObjectId())))

    publishers.update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Suscripciones: solo quien tiene acceso a la sucursal recibe eventos
# ---------------------------------------------------------------------------


def _info():
    return SimpleNamespace(context={})


def test_subscription_without_jwt_stays_open_but_never_emits(monkeypatch):
    access = AsyncMock()
    monkeypatch.setattr(subscriptions.access_checker, "require_branch_access", access)

    async def scenario():
        stream = subscriptions.OrderSubscription().branch_order_updated(
            info=_info(), branchId=BRANCH_ID
        )
        next_event = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.05)
        await subscriptions.publish_branch_order_update(BRANCH_ID, make_order())
        await asyncio.sleep(0.05)
        emitted = next_event.done()
        next_event.cancel()  # el cliente cierra la suscripción
        with contextlib.suppress(asyncio.CancelledError):
            await next_event
        await stream.aclose()
        return emitted

    assert run(scenario()) is False
    access.assert_not_awaited()


def test_subscription_rejects_user_without_branch_access(monkeypatch):
    monkeypatch.setattr(subscriptions, "require_auth", lambda jwt, info: USER_ID)
    monkeypatch.setattr(
        subscriptions.access_checker,
        "require_branch_access",
        AsyncMock(side_effect=Exception("No autorizado para acceder a esta sucursal")),
    )

    async def scenario():
        stream = subscriptions.OrderSubscription().new_branch_order(
            info=_info(), branchId=BRANCH_ID, jwt="token"
        )
        await stream.__anext__()

    with pytest.raises(Exception, match="No autorizado"):
        run(scenario())


def test_status_change_reaches_authorized_subscriber_end_to_end(monkeypatch, service):
    """Pubsub en memoria real: update_status → branchOrderUpdated."""
    monkeypatch.setattr(subscriptions, "require_auth", lambda jwt, info: USER_ID)
    access = AsyncMock(return_value=None)
    monkeypatch.setattr(subscriptions.access_checker, "require_branch_access", access)
    service.orders_repo = InMemoryOrders(make_order(OrderStatus.AWAITING_DELIVERY_ACCEPTANCE))
    order_id = str(service.orders_repo.order.id)

    async def scenario():
        stream = subscriptions.OrderSubscription().branch_order_updated(
            info=_info(), branchId=BRANCH_ID, jwt="token"
        )
        next_event = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.05)  # deja que la suscripción se registre
        await service.update_status(order_id, OrderStatus.ACCEPTED, orders_module.OrderActor.DELIVERY)
        event = await asyncio.wait_for(next_event, timeout=1)
        await stream.aclose()
        return event

    event = run(scenario())
    assert event.id == order_id
    assert event.status.value == OrderStatus.ACCEPTED.value
    access.assert_awaited_once_with(USER_ID, BRANCH_ID)
    # Al cerrar la suscripción no quedan colas colgando.
    assert f"branch_updates:{BRANCH_ID}" not in subscriptions.order_pubsub._subscribers
