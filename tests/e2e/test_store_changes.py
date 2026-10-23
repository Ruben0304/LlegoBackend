"""La tienda cambia o rechaza el pedido y el cliente reacciona."""

import pytest

from .flows import World


def test_store_removes_item_and_customer_accepts(world: World):
    order = world.create_order(items=world.items(burger=2, soda=1))
    modified = world.modify(order["id"], world.items(burger=2), reason="Se acabo el refresco")
    assert modified["status"] == "MODIFIED_BY_STORE"
    assert modified["subtotal"] == world.expected_subtotal(burger=2)
    assert modified["total"] < order["total"]
    assert modified["isEditable"] is True

    resubmitted = world.accept_modifications(order["id"])
    assert resubmitted["status"] == "PENDING_ACCEPTANCE"
    world.accept(order["id"])
    world.courier_accept(order["id"])
    assert world.deliver(order["id"])["status"] == "DELIVERED"


def test_store_modifies_and_customer_walks_away(world: World):
    order = world.create_order()
    world.modify(order["id"], world.items(burger=1))
    assert world.reject_modifications(order["id"])["status"] == "CANCELLED"


def test_store_rejects_and_customer_edits_and_resubmits(world: World):
    order = world.create_order(items=world.items(burger=3))
    assert world.reject(order["id"], "No nos quedan 3")["status"] == "REJECTED_BY_STORE"

    again = world.resubmit(order["id"], items=world.items(burger=1, soda=2))
    assert again["status"] == "PENDING_ACCEPTANCE"
    assert again["subtotal"] == world.expected_subtotal(burger=1, soda=2)
    assert world.accept(order["id"])["status"] == "AWAITING_DELIVERY_ACCEPTANCE"


def test_store_rejects_and_customer_gives_up(world: World):
    order = world.create_order()
    world.reject(order["id"])
    assert world.cancel_order(order["id"])["status"] == "CANCELLED"


def test_store_cannot_sneak_foreign_or_unavailable_products(world: World):
    order = world.create_order()
    assert world.modify_error(order["id"], world.items(foreign=1)).messages
    assert "no disponible" in str(world.modify_error(order["id"], world.items(unavailable=1)))
    # El pedido no cambio.
    assert world.get_order(order["id"])["status"] == "PENDING_ACCEPTANCE"


@pytest.mark.pagos
def test_store_sets_its_own_delivery_fee_before_payment(world: World):
    """M4: un envío más caro que el calculado lo tiene que aceptar el cliente."""
    order = world.create_order(payment="transfer")
    assert order["deliveryFee"] < 700.0
    changed = world.accept(order["id"], fee=700.0)
    assert changed["status"] == "MODIFIED_BY_STORE"
    assert changed["deliveryFee"] == 700.0
    assert changed["total"] == round(changed["subtotal"] + 700.0 + changed["serviceCharge"], 2)

    world.accept_modifications(order["id"])
    accepted = world.accept(order["id"])
    assert accepted["status"] == "AWAITING_DELIVERY_ACCEPTANCE"
    assert accepted["deliveryFee"] == 700.0


def test_cheaper_store_delivery_fee_needs_no_confirmation(world: World):
    order = world.create_order(payment="transfer")
    cheaper = round(order["deliveryFee"] / 2, 2)
    accepted = world.accept(order["id"], fee=cheaper)
    assert accepted["status"] == "AWAITING_DELIVERY_ACCEPTANCE"
    assert accepted["deliveryFee"] == cheaper


def test_delivery_fee_override_is_validated(world: World):
    order = world.create_order(payment="cash")
    assert "negativo" in str(world.accept_error(order["id"], fee=-5.0))
    pickup = world.create_order(payment="cash", pickup=True)
    assert "no lleva envio" in str(world.accept_error(pickup["id"], fee=100.0))
    # Ninguno de los intentos fallidos toco el dinero del pedido.
    assert world.get_order(order["id"])["total"] == order["total"]


def test_store_cannot_accept_the_same_order_twice(world: World):
    order = world.create_order()
    world.accept(order["id"])
    assert "ya no esta pendiente" in str(world.accept_error(order["id"], fee=999.0))
    assert world.get_order(order["id"])["deliveryFee"] == order["deliveryFee"]


@pytest.mark.pagos
def test_amount_to_pay_matches_order_total(world: World):
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])
    assert attempt["totalAmount"] == order["total"]
