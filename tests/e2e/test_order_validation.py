"""Pedidos que el backend debe rechazar (o aceptar) al crearlos."""

import pytest

from .flows import World


def test_server_computes_prices_from_catalog(world: World):
    order = world.create_order(items=world.items(burger=3, soda=2))
    assert order["subtotal"] == world.expected_subtotal(burger=3, soda=2)
    by_id = {i["itemId"]: i for i in order["items"]}
    assert by_id[world.products["burger"]["id"]]["finalPrice"] == world.products["burger"]["price"]


def test_product_from_another_branch_is_rejected(world: World):
    err = world.create_order_error(world.order_input(items=world.items(burger=1, foreign=1)))
    assert "no pertenece a esta sucursal" in str(err)


def test_unavailable_product_is_rejected(world: World):
    err = world.create_order_error(world.order_input(items=world.items(unavailable=1)))
    assert "no disponible" in str(err)


def test_invalid_quantities_and_empty_orders_are_rejected(world: World):
    assert "mayor que 0" in str(world.create_order_error(world.order_input(items=world.items(burger=0))))
    assert "mayor que 0" in str(world.create_order_error(world.order_input(items=world.items(burger=-2))))
    assert "al menos un" in str(world.create_order_error(world.order_input(items=[])))


def test_delivery_needs_an_address_and_pickup_must_not_have_one(world: World):
    no_address = world.order_input()
    no_address.pop("deliveryAddress")
    assert "INVALID_FULFILLMENT_INPUT" in world.create_order_error(no_address).codes

    pickup_with_address = world.order_input(pickup=True)
    pickup_with_address["deliveryAddress"] = dict(world.address)
    assert "INVALID_FULFILLMENT_INPUT" in world.create_order_error(pickup_with_address).codes


def test_payment_method_the_branch_does_not_offer_is_rejected(world: World, client):
    other = World.create(client)  # metodos de pago de OTRO mundo
    order_input = world.order_input()
    order_input["paymentMethod"] = other.payment_methods["cash"]["id"]
    assert "PAYMENT_METHOD_NOT_AVAILABLE" in world.create_order_error(order_input).codes


def test_paused_branch_rejects_orders_until_it_resumes(world: World):
    world.patch_branch(acceptingOrders=False)
    assert "BRANCH_NOT_ACCEPTING_ORDERS" in world.create_order_error(world.order_input()).codes
    world.patch_branch(acceptingOrders=True)
    assert world.create_order()["status"] == "PENDING_ACCEPTANCE"


def test_closed_branch_rejects_immediate_delivery(world: World):
    world.patch_branch(temporarilyClosed=True)
    assert "cerrada" in str(world.create_order_error(world.order_input()))
    assert "BRANCH_CLOSED_FOR_PICKUP" in world.create_order_error(
        world.order_input(pickup=True)
    ).codes


def test_inactive_or_catalog_only_branch_rejects_orders(world: World):
    world.patch_branch(catalogOnly=True)
    assert "solo muestra su catálogo" in str(world.create_order_error(world.order_input()))
    world.patch_branch(catalogOnly=False, isActive=False)
    assert "no está activa" in str(world.create_order_error(world.order_input()))


def test_branch_pausing_mid_flow_does_not_break_existing_orders(world: World):
    """Un pedido ya creado sigue su curso aunque la tienda pause nuevos pedidos."""
    order = world.create_order()
    world.patch_branch(acceptingOrders=False)
    world.accept(order["id"])
    world.courier_accept(order["id"])
    assert world.deliver(order["id"])["status"] == "DELIVERED"


@pytest.mark.xfail(
    strict=True,
    reason="MUY_IMPORTANTE_RESOLVER B6: acceptOrderForPayment no revisa si el mensajero "
    "ya lleva otro pedido y le pisa currentOrderId; el chequeo de confirmPickup queda anulado",
)
def test_courier_cannot_hold_two_orders_at_once_when_picking_up(world: World):
    first = world.create_order()
    world.accept(first["id"])
    world.courier_accept(first["id"])
    world.start_preparing(first["id"])
    world.mark_ready(first["id"])
    world.courier_pickup(first["id"])  # en camino con el primero

    second = world.create_order()
    world.accept(second["id"])
    world.courier_accept(second["id"])
    world.start_preparing(second["id"])
    world.mark_ready(second["id"])
    err = world.client.gql_error(
        """mutation($id: String!, $jwt: String!) { confirmPickup(orderId: $id, jwt: $jwt) { id } }""",
        {"id": second["id"], "jwt": world.token("courier")},
    )
    assert "otro pedido en curso" in str(err)
