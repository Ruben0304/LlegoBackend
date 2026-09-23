"""El dinero del cliente nunca se pierde ni se cobra dos veces."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from .flows import World

pytestmark = pytest.mark.pagos


def _paying_order(world: World):
    """Pedido en PENDING_PAYMENT con el cliente ya en la pantalla de pago."""
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])
    return order, attempt


def _payment_sent_order(world: World):
    order, attempt = _paying_order(world)
    world.confirm_payment_sent(attempt["id"])
    return order, attempt


# --------------------------------------------- nada cambia con el pago en curso


def test_store_cannot_modify_once_customer_started_paying(world: World):
    order, _ = _paying_order(world)
    assert "No se puede modificar" in str(world.modify_error(order["id"], world.items(burger=1)))


def test_store_cannot_modify_a_paid_order(world: World):
    order = world.paid_transfer_order()
    assert "No se puede modificar" in str(world.modify_error(order["id"], world.items(burger=1)))
    after = world.get_order(order["id"])
    assert after["status"] == "ACCEPTED"
    assert after["paymentStatus"] == "COMPLETED"


def test_store_cannot_reject_a_paid_order(world: World):
    order = world.paid_transfer_order()
    assert "No se puede rechazar" in str(world.reject_error(order["id"]))


def test_customer_cannot_resubmit_while_paying(world: World):
    order, _ = _paying_order(world)
    assert "No se puede reenviar" in str(world.resubmit_error(order["id"]))


def test_courier_can_release_before_payment_and_another_takes_it(world: World):
    order = world.delivery_order_ready_to_pay()
    released = world.courier_release(order["id"])
    assert released["status"] == "AWAITING_DELIVERY_ACCEPTANCE"
    assert released["deliveryPersonId"] is None
    assert world.courier_accept(order["id"], actor="courier2")["status"] == "PENDING_PAYMENT"


def test_courier_cannot_release_while_customer_pays(world: World):
    order, _ = _paying_order(world)
    assert "No puedes soltar" in str(world.courier_release_error(order["id"]))


def test_courier_app_cancel_button_goes_through_safe_path(world: World):
    """AppMensajeros "Cancelar pedido" usa updateOrderStatus -> espera de mensajero."""
    order = world.delivery_order_ready_to_pay()
    released = world.set_status(order["id"], "AWAITING_DELIVERY_ACCEPTANCE", actor="courier")
    assert released["status"] == "AWAITING_DELIVERY_ACCEPTANCE"
    assert released["deliveryPersonId"] is None  # antes quedaba trabado

    order = world.delivery_order_ready_to_pay()
    world.initiate_payment(order["id"])
    err = world.set_status_error(order["id"], "AWAITING_DELIVERY_ACCEPTANCE", "courier")
    assert "No puedes soltar" in str(err)


# ------------------------------------------------------ cancelar con / sin dinero


def test_customer_cancels_before_paying_and_payment_is_voided(world: World):
    order, attempt = _paying_order(world)
    assert world.cancel_order(order["id"])["status"] == "CANCELLED"
    assert world.payment_attempts(order["id"])[0]["status"] == "CANCELLED"
    assert "Estado no válido" in str(world.confirm_payment_sent_error(attempt["id"]))


def test_customer_cannot_cancel_after_sending_payment(world: World):
    order, _ = _payment_sent_order(world)
    assert "No se puede cancelar" in str(world.cancel_order_error(order["id"]))
    assert world.get_order(order["id"])["status"] == "PAYMENT_IN_PROGRESS"


def test_customer_cannot_cancel_while_preparing(world: World):
    order = world.paid_transfer_order()
    world.start_preparing(order["id"])
    assert world.cancel_order_error(order["id"]).messages


# ---------------------------------------------------------- reintentos y carreras


def test_payment_sent_retry_is_idempotent(world: World):
    order, attempt = _payment_sent_order(world)
    again = world.confirm_payment_sent(attempt["id"])  # la respuesta se perdio
    assert again["status"] == "AWAITING_BUSINESS"
    assert world.get_order(order["id"])["status"] == "PAYMENT_IN_PROGRESS"


def test_old_app_pay_button_after_sending_cannot_charge_twice(world: World):
    order, _ = _payment_sent_order(world)
    assert "Ya enviaste el pago" in str(world.initiate_payment_error(order["id"]))
    assert len(world.payment_attempts(order["id"])) == 1


def test_switching_payment_method_before_paying_voids_the_old_attempt(world: World):
    order, attempt = _paying_order(world)
    cash_attempt = world.initiate_payment(order["id"], method="cash")
    assert cash_attempt["id"] != attempt["id"]
    statuses = {a["id"]: a["status"] for a in world.payment_attempts(order["id"])}
    assert statuses[attempt["id"]] == "CANCELLED"


def test_business_double_confirmation_is_idempotent(world: World):
    order, attempt = _payment_sent_order(world)
    world.confirm_payment_received(attempt["id"])
    assert world.confirm_payment_received(attempt["id"])["status"] == "COMPLETED"
    order = world.get_order(order["id"])
    assert order["requiresAttention"] is False
    assert _count_payment_confirmations(order) == 1


def test_concurrent_confirmations_complete_the_payment_once(world: World):
    """Dueno y empleado (o doble toque) confirman el mismo pago a la vez."""
    order, attempt = _payment_sent_order(world)
    clients = [world.client.clone() for _ in range(6)]
    actors = ["owner", "staff"] * 3

    def confirm(pair):
        client, actor = pair
        try:
            return world.confirm_payment_received(attempt["id"], actor=actor, client=client)["status"]
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(confirm, zip(clients, actors)))

    assert set(results) == {"COMPLETED"}
    order = world.get_order(order["id"])
    assert order["status"] == "ACCEPTED"
    assert order["paymentStatus"] == "COMPLETED"
    assert order["requiresAttention"] is False
    assert _count_payment_confirmations(order) == 1


def _count_payment_confirmations(order) -> int:
    return sum(
        1
        for t in order["timeline"]
        if t["status"] == "ACCEPTED" and "Pago confirmado" in t["message"]
    )


# ------------------------------------------------------------ casos de soporte


def test_disputed_payment_goes_to_support_and_can_still_be_confirmed(world: World):
    order, attempt = _payment_sent_order(world)
    assert world.dispute_payment(attempt["id"], "No veo la transferencia")["status"] == "DISPUTED"
    assert world.get_order(order["id"])["requiresAttention"] is True
    # Una disputa nunca se cancela sola.
    assert world.expire(order["id"])["result"] == "escalated"
    # El negocio revisa de nuevo y si llego: se confirma.
    world.confirm_payment_received(attempt["id"])
    assert world.get_order(order["id"])["status"] == "ACCEPTED"


def test_payment_confirmed_after_cancellation_is_flagged_for_refund(world: World):
    order, attempt = _payment_sent_order(world)
    cancelled = world.force_status(order["id"], "CANCELLED")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["requiresAttention"] is True  # cancelado con dinero adentro

    world.confirm_payment_received(attempt["id"])
    order = world.get_order(order["id"])
    assert order["status"] == "CANCELLED"  # no se "revive"
    assert order["paymentStatus"] == "COMPLETED"  # pero el pago queda registrado
    assert order["requiresAttention"] is True
    assert order["id"] in {o["id"] for o in world.orders_requiring_attention()}


# ------------------------------------------------------ cuando y quien puede pagar


def test_cash_is_collected_only_on_delivery(world: World):
    order = world.create_order(payment="cash")
    world.accept(order["id"])
    order = world.courier_accept(order["id"])
    assert order["status"] == "ACCEPTED"
    assert order["paymentStatus"] == "PENDING"
    # Un pedido en efectivo nunca pasa por la pantalla de pago.
    assert "no está en un estado que permita pago" in str(world.initiate_payment_error(order["id"]))
    assert world.deliver(order["id"])["paymentStatus"] == "COMPLETED"


def test_customer_cannot_pay_before_store_and_courier_accept(world: World):
    order = world.create_order(payment="transfer")
    assert "no está en un estado que permita pago" in str(world.initiate_payment_error(order["id"]))
    world.accept(order["id"])
    assert "no está en un estado que permita pago" in str(world.initiate_payment_error(order["id"]))
    assert world.payment_attempts(order["id"]) == []


def test_payment_method_the_branch_does_not_offer_is_rejected(world: World, client):
    order = world.delivery_order_ready_to_pay()
    other = World.create(client)  # metodos de pago de OTRA sucursal
    err = world.client.gql_error(
        """mutation($o: String!, $pm: String!, $jwt: String!) {
          initiatePayment(orderId: $o, paymentMethodId: $pm, jwt: $jwt) { paymentAttempt { id } } }""",
        {"o": order["id"], "pm": other.payment_methods["transfer"]["id"], "jwt": world.token("customer")},
    )
    assert "no tiene habilitado" in str(err)
    assert world.payment_attempts(order["id"]) == []


def test_another_customer_cannot_pay_or_confirm_someone_elses_order(world: World):
    order, attempt = _paying_order(world)
    assert "No autorizado" in str(world.initiate_payment_error(order["id"], actor="customer2"))
    assert "No autorizado" in str(world.confirm_payment_sent_error(attempt["id"], actor="customer2"))
    assert world.get_order(order["id"])["status"] == "PENDING_PAYMENT"


def test_customer_cannot_confirm_their_own_payment_as_received(world: World):
    _, attempt = _payment_sent_order(world)
    assert world.confirm_payment_received_error(attempt["id"], "customer").messages
    assert world.confirm_payment_received_error(attempt["id"], "courier").messages


def test_proof_is_visible_to_the_store_but_not_to_strangers(world: World):
    order, attempt = _paying_order(world)
    proof = "https://example.com/comprobante-e2e.jpg"
    world.confirm_payment_sent(attempt["id"], proof=proof)
    assert world.active_attempt(order["id"], actor="owner")["proofUrl"] == proof
    assert world.active_attempt(order["id"], actor="staff")["proofUrl"] == proof
    for actor in ("stranger", "customer2"):
        assert "No autorizado" in str(
            world.client.gql_error(
                "query($o: String!, $jwt: String!) { activePaymentAttempt(orderId: $o, jwt: $jwt) { id } }",
                {"o": order["id"], "jwt": world.token(actor)},
            )
        ), actor


def test_amount_charged_reflects_the_store_delivery_fee(world: World):
    order = world.create_order(payment="transfer")
    world.accept(order["id"], fee=700.0)
    world.courier_accept(order["id"])
    attempt = world.initiate_payment(order["id"])
    # comision 0 en el mundo de prueba: subtotal + envio fijado por la tienda
    assert attempt["totalAmount"] == round(order["subtotal"] + 700.0, 2)


def test_paid_order_withstands_every_attempt_to_change_it(world: World):
    """Una vez cobrado, nada puede dejar al cliente sin pedido o cobrarle de nuevo."""
    order = world.paid_transfer_order()
    oid = order["id"]
    assert world.modify_error(oid, world.items(burger=1)).messages
    assert world.reject_error(oid).messages
    assert world.cancel_order_error(oid).messages
    assert world.resubmit_error(oid).messages
    assert world.courier_release_error(oid).messages
    assert world.initiate_payment_error(oid).messages
    assert world.accept_error(oid, fee=1.0).messages

    after = world.get_order(oid)
    assert after["status"] == "ACCEPTED"
    assert after["paymentStatus"] == "COMPLETED"
    assert after["total"] == order["total"]
    assert len(world.payment_attempts(oid)) == 1
    assert world.deliver(oid)["paymentStatus"] == "COMPLETED"
