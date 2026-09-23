"""Flujos completos de punta a punta que TIENEN que funcionar siempre."""

import pytest

from .flows import World


def ids(orders):
    return {o["id"] for o in orders}


def statuses(order):
    return [t["status"] for t in order["timeline"]]


def assert_is_subsequence(expected, actual):
    it = iter(actual)
    missing = [s for s in expected if s not in it]
    assert not missing, f"Faltan estados {missing} en el timeline {actual}"


def assert_money_consistent(world: World, order, **quantities):
    # El precio lo calcula el servidor con el catalogo, no lo manda la app.
    assert order["subtotal"] == world.expected_subtotal(**quantities)
    assert order["serviceCharge"] == round(order["subtotal"] * world.service_fee_rate, 2)
    assert order["total"] == round(
        order["subtotal"] + order["deliveryFee"] + order["serviceCharge"], 2
    )


@pytest.mark.pagos
def test_cash_delivery_order_is_delivered_and_rated(world: World):
    """Cliente pide en efectivo -> negocio acepta -> mensajero acepta -> se prepara
    -> se entrega con codigo -> cliente califica."""
    order = world.create_order(payment="cash", comments="Sin cebolla, por favor")
    order_id = order["id"]
    assert order["status"] == "PENDING_ACCEPTANCE"
    assert order["deliveryMode"] == "app"
    assert order["deliveryFee"] > 0
    assert_money_consistent(world, order, burger=2, soda=1)

    assert order_id in ids(world.branch_orders()["orders"])
    assert order_id in ids(world.my_orders())

    order = world.accept(order_id, minutes=25)
    assert order["status"] == "AWAITING_DELIVERY_ACCEPTANCE"

    # Mensajero que nunca habia aceptado un pedido (se le crea el perfil al vuelo).
    order = world.courier_accept(order_id)
    assert order["status"] == "ACCEPTED"
    assert order["paymentStatus"] == "PENDING"  # efectivo: se cobra al entregar

    order = world.deliver(order_id)
    assert order["status"] == "DELIVERED"
    assert order["paymentStatus"] == "COMPLETED"
    assert order["deliveryVerificationCode"] is None  # ya no se expone

    order = world.rate(order_id, 5, "Llego caliente y rapido")
    assert order["rating"] == 5
    assert order["ratingComment"] == "Llego caliente y rapido"
    assert "ya fue calificado" in str(world.rate_error(order_id, 1))

    assert_is_subsequence(
        [
            "PENDING_ACCEPTANCE",
            "AWAITING_DELIVERY_ACCEPTANCE",
            "ACCEPTED",
            "PREPARING",
            "READY_FOR_PICKUP",
            "ON_THE_WAY",
            "DELIVERED",
        ],
        statuses(order),
    )


@pytest.mark.pagos
def test_transfer_delivery_order_is_paid_confirmed_and_delivered(world: World):
    """Cliente pide por transferencia -> acepta negocio y mensajero -> cliente paga
    (con reintento) -> negocio confirma -> entrega -> calificacion."""
    order = world.delivery_order_ready_to_pay()
    order_id = order["id"]
    assert order["status"] == "PENDING_PAYMENT"
    assert order["canCancel"] is True

    # El negocio no puede empezar a preparar sin cobrar.
    assert world.set_status_error(order_id, "PREPARING", "owner").messages
    assert world.get_order(order_id)["status"] == "PENDING_PAYMENT"

    attempt = world.initiate_payment(order_id)
    assert attempt["status"] == "AWAITING_PROOF"

    # El cliente cierra la app y vuelve a tocar "Pagar": se retoma el mismo pago.
    again = world.initiate_payment(order_id)
    assert again["id"] == attempt["id"]

    sent = world.confirm_payment_sent(attempt["id"])
    assert sent["status"] == "AWAITING_BUSINESS"
    order = world.get_order(order_id)
    assert order["status"] == "PAYMENT_IN_PROGRESS"
    assert order["canCancel"] is False

    # El negocio encuentra el pago pendiente de confirmar.
    assert world.active_attempt(order_id)["id"] == attempt["id"]
    confirmed = world.confirm_payment_received(attempt["id"])
    assert confirmed["status"] == "COMPLETED"

    order = world.get_order(order_id)
    assert order["status"] == "ACCEPTED"
    assert order["paymentStatus"] == "COMPLETED"
    assert order["deadlineAt"] is not None

    order = world.deliver(order_id)
    assert order["status"] == "DELIVERED"
    assert world.rate(order_id, 4, "Bien")["rating"] == 4


@pytest.mark.pagos
def test_invited_staff_can_run_the_whole_business_side(world: World):
    """Un empleado (manager de la sucursal, no dueno) acepta, confirma el pago y
    prepara. Antes confirmPaymentReceived le daba "No autorizado"."""
    order = world.create_order(payment="transfer")
    world.accept(order["id"], actor="staff")
    world.courier_accept(order["id"])
    attempt = world.initiate_payment(order["id"])
    world.confirm_payment_sent(attempt["id"], proof="https://example.com/comprobante.jpg")
    assert world.confirm_payment_received(attempt["id"], actor="staff")["status"] == "COMPLETED"
    assert world.start_preparing(order["id"], actor="staff")["status"] == "PREPARING"
    assert world.mark_ready(order["id"], actor="staff")["status"] == "READY_FOR_PICKUP"


def test_customer_and_store_can_chat_on_the_order(world: World):
    order = world.create_order()
    world.comment(order["id"], "¿Pueden agregar servilletas?", actor="customer")
    world.comment(order["id"], "Claro que si", actor="owner")
    assert "No autorizado" in str(
        world.client.gql_error(
            """mutation($input: AddOrderCommentInput!, $jwt: String!) {
              addOrderComment(input: $input, jwt: $jwt) { id } }""",
            {"input": {"orderId": order["id"], "message": "hola"}, "jwt": world.token("stranger")},
        )
    )


def test_pickup_cash_order_goes_straight_to_accepted(world: World):
    order = world.create_order(payment="cash", pickup=True)
    assert order["deliveryMode"] == "pickup"
    assert order["deliveryFee"] == 0
    order = world.accept(order["id"])
    assert order["status"] == "ACCEPTED"  # sin mensajero
    world.start_preparing(order["id"])
    order = world.mark_ready(order["id"])
    assert order["status"] == "READY_FOR_PICKUP"
    # El cliente ve el codigo para recoger.
    assert len(world.get_order(order["id"])["deliveryVerificationCode"]) == 6


@pytest.mark.xfail(
    strict=True,
    reason="MUY_IMPORTANTE_RESOLVER B2: un pedido de recogida no se puede cerrar nunca",
)
def test_pickup_order_can_be_completed_by_the_store(world: World):
    order = world.create_order(payment="cash", pickup=True)
    world.accept(order["id"])
    world.start_preparing(order["id"])
    world.mark_ready(order["id"])
    world.set_status(order["id"], "DELIVERED", "owner")
    assert world.get_order(order["id"])["status"] == "DELIVERED"
