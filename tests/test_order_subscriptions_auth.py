"""Autorizacion de las subscriptions de pedidos (schema/orders/subscriptions.py).

orderTrackingStream solo comprobaba que el pedido existiera (context.md §12.5) y
orderUpdated, deliveryLocationUpdated, newBranchOrder y branchOrderUpdated no
pedian ni JWT: cualquiera con un id podia seguir la ubicacion del mensajero o
los pedidos de una sucursal ajena. couriersPresenceStream daba la ubicacion de
todos los mensajeros a cualquier usuario autenticado.

En orderUpdated, deliveryLocationUpdated, newBranchOrder y branchOrderUpdated
denegar no puede cerrar el stream al instante: LlegoBusiness (version actual) se
suscribe sin jwt y su SubscriptionManager.collectWithReconnect se vuelve a
suscribir en cuanto el stream termina, sin pausa. Sin credenciales el stream se
queda abierto sin emitir; con un JWT invalido o sin acceso el error llega tras
SUBSCRIPTION_DENIED_DELAY_SECONDS.

Sin red ni Mongo: repos y access_checker mockeados; la logica de acceso real
(OrderService.user_can_access_order) se ejecuta tal cual.
"""

import asyncio
import os
from datetime import datetime
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

import schema.orders.subscriptions as subs
from core.config import settings
from services.access_checker import access_checker
from services.orders_service import order_service
from utils.auth import create_access_token

ORDER_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"
CUSTOMER_ID = "507f1f77bcf86cd799439014"
COURIER_USER_ID = "507f1f77bcf86cd799439015"
COURIER_ID = "507f1f77bcf86cd799439016"
STAFF_ID = "507f1f77bcf86cd799439017"
STRANGER_ID = "507f1f77bcf86cd799439099"

# Espera antes de devolver el error de una subscription denegada (en produccion 30 s).
DENIED_DELAY = 0.2


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """JWT firmable, pedido de prueba y acceso a sucursal solo para STAFF_ID."""
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-subscriptions")
    monkeypatch.setattr(subs, "SUBSCRIPTION_DENIED_DELAY_SECONDS", DENIED_DELAY)
    order = SimpleNamespace(
        id=ORDER_ID,
        customerId=CUSTOMER_ID,
        branchId=BRANCH_ID,
        deliveryPersonId=COURIER_ID,
        status="on_the_way",
    )
    monkeypatch.setattr(subs.orders_repo, "get_by_id", AsyncMock(return_value=order))

    async def _branch_access(user_id, branch_id, require_owner=False):
        if user_id == STAFF_ID and branch_id == BRANCH_ID:
            return True, None
        return False, "No autorizado para acceder a esta sucursal"

    branch_access = AsyncMock(side_effect=_branch_access)
    monkeypatch.setattr(access_checker, "check_branch_access", branch_access)

    async def _courier_by_user(user_id):
        if user_id == COURIER_USER_ID:
            return SimpleNamespace(id=COURIER_ID, userId=COURIER_USER_ID)
        return None

    monkeypatch.setattr(
        order_service.delivery_repo, "get_by_user_id", AsyncMock(side_effect=_courier_by_user)
    )
    tracking = AsyncMock(return_value={"estimatedMinutes": 7, "distanceKm": 1.2})
    monkeypatch.setattr(order_service, "get_order_tracking", tracking)
    # Las subscriptions de pedido serializan con order_to_type; aqui da igual.
    monkeypatch.setattr(subs, "order_to_type", lambda order: order)
    subs.order_pubsub._subscribers.clear()
    yield SimpleNamespace(order=order, branch_access=branch_access, tracking=tracking)
    subs.order_pubsub._subscribers.clear()


def _info():
    info = MagicMock()
    info.context = {"user_id": None, "user_role": None}
    return info


def _jwt(user_id, role="customer"):
    return create_access_token({"user_id": user_id, "role": role})


async def _denied(gen, channel, match):
    with pytest.raises(Exception, match=match):
        await gen.__anext__()
    assert channel not in subs.order_pubsub._subscribers


async def _rejected_after_delay(gen, channel, match):
    """El error llega, pero no antes de SUBSCRIPTION_DENIED_DELAY_SECONDS."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(Exception, match=match):
        await gen.__anext__()
    assert loop.time() - started >= DENIED_DELAY * 0.9
    assert channel not in subs.order_pubsub._subscribers


async def _held_open(gen, channel):
    """Sin credenciales: ni error, ni eventos, ni canal; sigue abierta hasta
    que el cliente la cancela."""
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(DENIED_DELAY * 2)
    assert not task.done(), "la subscription termino y el cliente se reconectaria"
    assert channel not in subs.order_pubsub._subscribers
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _first_event(gen, channel, message):
    """Arranca la subscription, publica `message` en `channel` y devuelve lo emitido."""
    task = asyncio.ensure_future(gen.__anext__())
    for _ in range(50):
        await asyncio.sleep(0)
        if channel in subs.order_pubsub._subscribers:
            break
    assert channel in subs.order_pubsub._subscribers, "no llego a suscribirse"
    await subs.order_pubsub.publish(channel, message)
    value = await asyncio.wait_for(task, 1)
    await gen.aclose()
    return value


# ------------------------------------------------------------ orderTrackingStream


def test_tracking_stream_requires_jwt():
    gen = subs.OrderSubscription().order_tracking_stream(info=_info(), orderId=ORDER_ID)
    asyncio.run(_denied(gen, f"order_tracking:{ORDER_ID}", "Autenticación requerida"))


def test_tracking_stream_rejects_user_without_relation_to_the_order(env):
    gen = subs.OrderSubscription().order_tracking_stream(
        info=_info(), orderId=ORDER_ID, jwt=_jwt(STRANGER_ID)
    )
    asyncio.run(_denied(gen, f"order_tracking:{ORDER_ID}", "No autorizado"))
    env.tracking.assert_not_awaited()


@pytest.mark.parametrize(
    "user_id,role",
    [
        (CUSTOMER_ID, "customer"),  # cliente dueno
        (STAFF_ID, "customer"),  # dueno/manager de la sucursal
        (COURIER_USER_ID, "customer"),  # mensajero asignado
        (STRANGER_ID, "admin"),  # staff de plataforma
    ],
)
def test_tracking_stream_allows_order_parties(env, user_id, role):
    async def _run():
        gen = subs.OrderSubscription().order_tracking_stream(
            info=_info(), orderId=ORDER_ID, jwt=_jwt(user_id, role)
        )
        payload = await gen.__anext__()
        await gen.aclose()
        return payload

    payload = asyncio.run(_run())

    assert payload.estimatedMinutes == 7
    assert env.tracking.await_args.kwargs.get("bypass_authorization") is True


# ------------------------------------------- orderUpdated / deliveryLocationUpdated


def _location_update():
    return {
        "orderId": ORDER_ID,
        "longitude": -82.35,
        "latitude": 23.13,
        "timestamp": datetime(2026, 10, 1, 12, 0, 0),
    }


ORDER_SUBSCRIPTIONS = [
    ("order_updated", f"order:{ORDER_ID}"),
    ("delivery_location_updated", f"delivery_location:{ORDER_ID}"),
]


@pytest.mark.parametrize("name,channel", ORDER_SUBSCRIPTIONS)
def test_order_subscriptions_hold_anonymous_open(name, channel):
    gen = getattr(subs.OrderSubscription(), name)(info=_info(), orderId=ORDER_ID)
    asyncio.run(_held_open(gen, channel))


@pytest.mark.parametrize("name,channel", ORDER_SUBSCRIPTIONS)
@pytest.mark.parametrize(
    "jwt,match",
    [
        (lambda: _jwt(STRANGER_ID), "No autorizado"),
        (lambda: "no-es-un-jwt", "Invalid JWT"),
    ],
    ids=["sin_acceso", "jwt_invalido"],
)
def test_order_subscriptions_reject_after_delay(name, channel, jwt, match):
    gen = getattr(subs.OrderSubscription(), name)(info=_info(), orderId=ORDER_ID, jwt=jwt())
    asyncio.run(_rejected_after_delay(gen, channel, match))


@pytest.mark.parametrize("user_id", [CUSTOMER_ID, STAFF_ID, COURIER_USER_ID])
def test_delivery_location_streams_to_order_parties(user_id):
    gen = subs.OrderSubscription().delivery_location_updated(
        info=_info(), orderId=ORDER_ID, jwt=_jwt(user_id)
    )
    update = asyncio.run(_first_event(gen, f"delivery_location:{ORDER_ID}", _location_update()))

    assert update.orderId == ORDER_ID
    assert update.location.coordinates == [-82.35, 23.13]


def test_order_updated_streams_to_customer():
    gen = subs.OrderSubscription().order_updated(
        info=_info(), orderId=ORDER_ID, jwt=_jwt(CUSTOMER_ID)
    )
    assert asyncio.run(_first_event(gen, f"order:{ORDER_ID}", "pedido")) == "pedido"


# --------------------------------------------- newBranchOrder / branchOrderUpdated


BRANCH_SUBSCRIPTIONS = [
    ("new_branch_order", f"branch:{BRANCH_ID}"),
    ("branch_order_updated", f"branch_updates:{BRANCH_ID}"),
]


@pytest.mark.parametrize("name,channel", BRANCH_SUBSCRIPTIONS)
def test_branch_subscriptions_hold_anonymous_open(env, name, channel):
    gen = getattr(subs.OrderSubscription(), name)(info=_info(), branchId=BRANCH_ID)
    asyncio.run(_held_open(gen, channel))
    env.branch_access.assert_not_awaited()


@pytest.mark.parametrize("name,channel", BRANCH_SUBSCRIPTIONS)
def test_branch_subscriptions_reject_users_without_branch_access(name, channel):
    gen = getattr(subs.OrderSubscription(), name)(
        info=_info(), branchId=BRANCH_ID, jwt=_jwt(CUSTOMER_ID)
    )
    asyncio.run(
        _rejected_after_delay(gen, channel, "No autorizado para acceder a esta sucursal")
    )


def test_anonymous_subscription_logs_a_single_warning(caplog):
    gen = subs.OrderSubscription().new_branch_order(info=_info(), branchId=BRANCH_ID)
    with caplog.at_level("WARNING", logger=subs.logger.name):
        asyncio.run(_held_open(gen, f"branch:{BRANCH_ID}"))

    warnings = [r for r in caplog.records if r.name == subs.logger.name]
    assert len(warnings) == 1
    assert "newBranchOrder" in warnings[0].getMessage()


@pytest.mark.parametrize("name,channel", BRANCH_SUBSCRIPTIONS)
def test_branch_subscriptions_stream_to_branch_staff(name, channel):
    gen = getattr(subs.OrderSubscription(), name)(
        info=_info(), branchId=BRANCH_ID, jwt=_jwt(STAFF_ID)
    )
    assert asyncio.run(_first_event(gen, channel, "pedido")) == "pedido"


@pytest.mark.parametrize("name,channel", BRANCH_SUBSCRIPTIONS)
def test_branch_subscriptions_allow_platform_admin(env, name, channel):
    gen = getattr(subs.OrderSubscription(), name)(
        info=_info(), branchId=BRANCH_ID, jwt=_jwt(STRANGER_ID, "admin")
    )
    assert asyncio.run(_first_event(gen, channel, "pedido")) == "pedido"
    env.branch_access.assert_not_awaited()


# ------------------------------------------------------------ couriersPresenceStream


def test_couriers_presence_rejects_regular_users():
    gen = subs.OrderSubscription().couriers_presence_stream(
        info=_info(), jwt=_jwt(CUSTOMER_ID)
    )
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(gen.__anext__())


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_couriers_presence_streams_to_platform_staff(monkeypatch, role):
    snapshot = [SimpleNamespace(deliveryPersonId=COURIER_ID, isOnline=True)]
    monkeypatch.setattr(subs, "_redis_fetch_courier_presence_snapshot_sync", lambda: snapshot)
    monkeypatch.setattr(subs, "_enrich_courier_snapshot", AsyncMock(return_value=snapshot))

    async def _run():
        gen = subs.OrderSubscription().couriers_presence_stream(
            info=_info(), jwt=_jwt(STRANGER_ID, role)
        )
        first = await gen.__anext__()
        await gen.aclose()
        return first

    assert asyncio.run(_run()) == snapshot


# ------------------------------------------------------- protocolo WebSocket real
#
# Lo que ve la app: Apollo Kotlin 4 usa por defecto el protocolo legado
# graphql-ws. Antes del arreglo, newBranchOrder sin jwt recibia data{errors} y
# complete al instante, y collectWithReconnect se volvia a suscribir sin pausa.


@pytest.fixture(scope="module")
def ws_client():
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app, raise_server_exceptions=False)


WS_PROTOCOLS = {
    # protocolo: (mensaje de alta, mensaje de baja)
    "graphql-ws": ("start", "stop"),
    "graphql-transport-ws": ("subscribe", "complete"),
}

ANONYMOUS_QUERY = 'subscription { newBranchOrder(branchId: "%s") { id } }' % BRANCH_ID
WITH_JWT_QUERY = (
    'subscription ($jwt: String) { newBranchOrder(branchId: "%s", jwt: $jwt) { id } }'
    % BRANCH_ID
)


@pytest.mark.parametrize("protocol", list(WS_PROTOCOLS))
def test_ws_anonymous_subscription_is_not_completed(ws_client, protocol):
    """La operacion sin jwt no recibe nada; la denegada recibe su error tras la
    espera. Si la anonima terminara, sus mensajes llegarian antes."""
    start, stop = WS_PROTOCOLS[protocol]
    with ws_client.websocket_connect("/graphql", subprotocols=[protocol]) as ws:
        ws.send_json({"type": "connection_init", "payload": {}})
        assert ws.receive_json()["type"] == "connection_ack"

        ws.send_json({"id": "anonima", "type": start, "payload": {"query": ANONYMOUS_QUERY}})
        ws.send_json(
            {
                "id": "denegada",
                "type": start,
                "payload": {"query": WITH_JWT_QUERY, "variables": {"jwt": _jwt(CUSTOMER_ID)}},
            }
        )

        first = ws.receive_json()
        assert first["id"] == "denegada"
        if protocol == "graphql-ws":
            assert first["type"] == "data"
            assert "No autorizado" in first["payload"]["errors"][0]["message"]
            assert ws.receive_json() == {"type": "complete", "id": "denegada"}
        else:
            assert first["type"] == "error"
            assert "No autorizado" in first["payload"][0]["message"]

        ws.send_json({"id": "anonima", "type": stop})
