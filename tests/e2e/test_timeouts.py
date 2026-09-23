"""Que pasa cuando alguien no responde a tiempo.

`world.expire(order_id)` pone el plazo del pedido en el pasado y ejecuta la
MISMA logica que el worker de timeouts de produccion, solo para ese pedido.
Regla de oro: sin dinero de por medio se cancela; con dinero NUNCA se cancela
solo, se escala a soporte.
"""

import pytest

from .flows import World


def test_store_never_answers(world: World):
    order = world.create_order()
    result = world.expire(order["id"])
    assert result["result"] == "cancelled"
    assert result["status"] == "cancelled"

    order = world.get_order(order["id"])
    assert order["status"] == "CANCELLED"
    assert "la tienda no respondio" in order["timeline"][-1]["message"]

    # La tienda despierta tarde: ya no puede aceptarlo.
    assert "ya no esta pendiente" in str(world.accept_error(order["id"]))
    # El cliente no queda bloqueado: puede volver a pedir.
    assert world.create_order()["status"] == "PENDING_ACCEPTANCE"


def test_no_courier_accepts(world: World):
    order = world.create_order()
    world.accept(order["id"])
    assert world.expire(order["id"])["result"] == "cancelled"
    err = world.client.gql_error(
        """mutation($id: String!, $jwt: String!) {
          acceptOrderForPayment(orderId: $id, jwt: $jwt) { id } }""",
        {"id": order["id"], "jwt": world.token("courier")},
    )
    assert "esperando" in str(err)


@pytest.mark.pagos
def test_customer_never_pays(world: World):
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])  # abrio la pantalla y no pago

    assert world.expire(order["id"])["result"] == "cancelled"
    assert world.get_order(order["id"])["status"] == "CANCELLED"

    # El intento de pago queda anulado: la app ya no puede mostrar "¡Listo!".
    assert world.payment_attempts(order["id"])[0]["status"] == "CANCELLED"
    assert "Estado no válido" in str(world.confirm_payment_sent_error(attempt["id"]))
    assert world.initiate_payment_error(order["id"]).messages


@pytest.mark.pagos
def test_starting_to_pay_gives_the_customer_fresh_time(world: World):
    order = world.delivery_order_ready_to_pay()
    before = world.get_order(order["id"])["deadlineAt"]
    world.initiate_payment(order["id"])
    after = world.get_order(order["id"])["deadlineAt"]
    assert after >= before


@pytest.mark.pagos
def test_business_slow_to_confirm_transfer_is_escalated_not_cancelled(world: World):
    """El caso que mas dinero hacia perder: el cliente ya transfirio."""
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])
    world.confirm_payment_sent(attempt["id"])

    result = world.expire(order["id"])
    assert result["result"] == "escalated"
    assert result["status"] == "payment_in_progress"
    assert result["requiresAttention"] is True

    assert order["id"] in {o["id"] for o in world.orders_requiring_attention()}
    # Escalar no borra el plazo de nuevo: un segundo tick no hace nada.
    assert world.expire(order["id"])["result"] == "no_deadline"

    # El cliente no puede abandonar un pedido con su dinero adentro.
    assert "No se puede cancelar" in str(world.cancel_order_error(order["id"]))

    # El negocio confirma tarde: el pedido sigue su curso normal.
    world.confirm_payment_received(attempt["id"])
    order = world.get_order(order["id"])
    assert order["status"] == "ACCEPTED"
    assert order["paymentStatus"] == "COMPLETED"
    assert world.deliver(order["id"])["status"] == "DELIVERED"


@pytest.mark.pagos
def test_paid_order_the_store_does_not_start_is_escalated(world: World):
    order = world.paid_transfer_order()
    result = world.expire(order["id"])
    assert result["result"] == "escalated"
    assert result["status"] == "accepted"
    assert result["paymentStatus"] == "completed"
    assert "no inicio la elaboracion" in result["attentionReason"]
    # Sigue siendo entregable.
    assert world.deliver(order["id"])["status"] == "DELIVERED"


def test_cash_order_the_store_does_not_start_is_cancelled_and_courier_freed(world: World):
    order = world.create_order(payment="cash")
    world.accept(order["id"])
    world.courier_accept(order["id"])
    assert world.expire(order["id"])["result"] == "cancelled"

    # El mensajero queda libre para el siguiente pedido.
    other = world.create_order(payment="cash")
    world.accept(other["id"])
    assert world.courier_accept(other["id"])["status"] == "ACCEPTED"


def test_customer_ignores_store_modifications(world: World):
    order = world.create_order()
    world.modify(order["id"], world.items(burger=1))
    assert world.expire(order["id"])["result"] == "cancelled"


@pytest.mark.pagos
def test_orders_in_preparation_have_no_timeout(world: World):
    order = world.paid_transfer_order()
    world.start_preparing(order["id"])
    assert world.expire(order["id"])["result"] == "no_deadline"
    assert world.get_order(order["id"])["status"] == "PREPARING"
