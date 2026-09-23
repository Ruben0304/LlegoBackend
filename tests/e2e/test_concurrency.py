"""Carreras reales: dos personas tocando el mismo pedido al mismo tiempo."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from .client import GraphQLFailure
from .flows import World


def _parallel(fn, args_list):
    with ThreadPoolExecutor(max_workers=len(args_list)) as pool:
        return list(pool.map(lambda args: fn(*args), args_list))


def test_two_couriers_race_for_the_same_order_only_one_wins(world: World):
    order = world.create_order()
    world.accept(order["id"])

    def take(actor):
        client = world.client.clone()
        try:
            return actor, world.courier_accept(order["id"], actor=actor, client=client)
        except GraphQLFailure as failure:
            return actor, failure
        finally:
            client.close()

    results = _parallel(take, [("courier",), ("courier2",)] * 2)
    winners = {actor for actor, r in results if not isinstance(r, GraphQLFailure)}
    assert len(winners) == 1, results
    for actor, r in results:
        if isinstance(r, GraphQLFailure):
            assert "tomado por otro" in str(r) or "esperando" in str(r), r

    final = world.get_order(order["id"])
    assert final["status"] == "ACCEPTED"
    assert final["deliveryPersonId"] is not None


def test_store_timeout_racing_with_acceptance_leaves_a_consistent_order(world: World):
    """El worker vence el pedido mientras la tienda lo acepta: gana uno y el
    pedido queda en un estado coherente (nunca aceptado Y cancelado)."""
    order = world.create_order()

    def accept():
        client = world.client.clone()
        try:
            return client.gql(
                """mutation($id: String!, $jwt: String!) {
                  acceptOrder(orderId: $id, estimatedMinutes: 10, jwt: $jwt) { status } }""",
                {"id": order["id"], "jwt": world.token("owner")},
            )["acceptOrder"]["status"]
        except GraphQLFailure as failure:
            return f"error: {failure}"
        finally:
            client.close()

    def expire():
        client = world.client.clone()
        try:
            return client.rest("POST", f"/e2e/orders/{order['id']}/expire")["result"]
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = pool.submit(accept)
        expired = pool.submit(expire)
        accept_result, expire_result = accepted.result(), expired.result()

    final = world.get_order(order["id"])["status"]
    if final == "CANCELLED":
        assert accept_result.startswith("error"), (accept_result, expire_result)
    else:
        assert final == "AWAITING_DELIVERY_ACCEPTANCE", (accept_result, expire_result)
        assert expire_result in {"skipped", "no_deadline"}, expire_result


@pytest.mark.xfail(
    strict=True,
    reason="MUY_IMPORTANTE_RESOLVER C3: doble toque en 'Pedir' crea dos pedidos "
    "(no hay idempotency key)",
)
def test_double_tap_on_order_button_creates_a_single_order(world: World):
    order_input = world.order_input()

    def create():
        client = world.client.clone()
        try:
            return client.gql(
                world.CREATE_ORDER, {"input": order_input, "jwt": world.token("customer")}
            )["createOrder"]["id"]
        finally:
            client.close()

    _parallel(create, [(), ()])
    assert len(world.my_orders()) == 1


@pytest.mark.xfail(
    strict=True,
    reason="MUY_IMPORTANTE_RESOLVER E3: el codigo de entrega no tiene limite de intentos",
)
def test_delivery_code_is_locked_after_many_wrong_attempts(world: World):
    order = world.create_order()
    world.accept(order["id"])
    world.courier_accept(order["id"])
    world.start_preparing(order["id"])
    world.mark_ready(order["id"])
    world.courier_pickup(order["id"])
    real = world.get_order(order["id"])["deliveryVerificationCode"]
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(10):
        world.courier_deliver_error(order["id"], wrong)
    # Tras 10 intentos fallidos incluso el codigo correcto deberia bloquearse.
    assert world.courier_deliver_error(order["id"], real).messages
