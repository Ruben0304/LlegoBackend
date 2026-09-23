"""Cada actor solo puede hacer lo que le toca (E1/E2 del documento de hallazgos)."""

import pytest

from .flows import World


@pytest.fixture
def order_on_the_way(world: World):
    order = world.create_order(payment="cash")
    world.accept(order["id"])
    world.courier_accept(order["id"])
    world.start_preparing(order["id"])
    world.mark_ready(order["id"])
    world.courier_pickup(order["id"])
    return order


@pytest.mark.pagos
def test_stranger_cannot_see_or_touch_someone_elses_order(world: World):
    order = world.create_order(payment="transfer")
    oid = order["id"]
    assert "No autorizado" in str(world.get_order_error(oid, "stranger"))
    assert "No autorizado" in str(world.cancel_order_error(oid, "stranger"))
    assert world.accept_error(oid, actor="stranger").messages
    assert world.set_status_error(oid, "CANCELLED", "stranger").messages
    assert world.mark_ready_error(oid, "stranger").messages
    assert "No autorizado" in str(
        world.client.gql_error(
            "query($o: String!, $jwt: String!) { paymentAttemptsByOrder(orderId: $o, jwt: $jwt) { id } }",
            {"o": oid, "jwt": world.token("stranger")},
        )
    )
    # Otro cliente tampoco.
    assert "No autorizado" in str(world.get_order_error(oid, "customer2"))
    assert world.get_order(oid)["status"] == "PENDING_ACCEPTANCE"


def test_each_participant_can_see_the_order(world: World):
    order = world.delivery_order_ready_to_pay()
    for actor in ("customer", "owner", "staff", "courier", "admin"):
        assert world.get_order(order["id"], actor=actor)["id"] == order["id"], actor


@pytest.mark.pagos
def test_customer_cannot_skip_payment(world: World):
    order = world.delivery_order_ready_to_pay()
    assert world.set_status_error(order["id"], "ACCEPTED", "customer").messages
    assert "Acceso denegado" in str(world.force_status_error(order["id"], "ACCEPTED", "customer"))
    assert world.get_order(order["id"])["status"] == "PENDING_PAYMENT"


def test_store_cannot_skip_payment_or_the_delivery_code(world: World, order_on_the_way):
    oid = order_on_the_way["id"]
    assert "no puede pasar" in str(world.set_status_error(oid, "DELIVERED", "owner"))
    assert world.get_order(oid)["status"] == "ON_THE_WAY"

    unpaid = world.delivery_order_ready_to_pay()
    assert "no puede pasar" in str(world.set_status_error(unpaid["id"], "ACCEPTED", "owner"))


@pytest.mark.pagos
def test_store_cannot_confirm_its_own_payment_before_customer_sends_it(world: World):
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])
    assert "Estado no válido" in str(world.confirm_payment_received_error(attempt["id"], "owner"))


@pytest.mark.pagos
def test_other_business_cannot_confirm_payment(world: World):
    order = world.delivery_order_ready_to_pay()
    attempt = world.initiate_payment(order["id"])
    world.confirm_payment_sent(attempt["id"])
    # "stranger" es dueno de OTRO negocio del mismo mundo.
    assert world.confirm_payment_received_error(attempt["id"], "stranger").messages
    assert world.get_order(order["id"])["paymentStatus"] == "PENDING"


def test_wrong_delivery_code_is_rejected(world: World, order_on_the_way):
    oid = order_on_the_way["id"]
    real = world.get_order(oid)["deliveryVerificationCode"]
    wrong = "000000" if real != "000000" else "111111"
    assert "incorrecto" in str(world.courier_deliver_error(oid, wrong))
    assert world.get_order(oid)["status"] == "ON_THE_WAY"


def test_other_courier_cannot_deliver(world: World, order_on_the_way):
    oid = order_on_the_way["id"]
    code = world.get_order(oid)["deliveryVerificationCode"]
    assert "No autorizado" in str(world.courier_deliver_error(oid, code, actor="courier2"))


def test_only_the_customer_sees_the_delivery_code(world: World, order_on_the_way):
    oid = order_on_the_way["id"]
    assert world.get_order(oid, "customer")["deliveryVerificationCode"]
    for actor in ("courier", "owner", "admin"):
        assert world.get_order(oid, actor)["deliveryVerificationCode"] is None, actor


def test_store_only_sees_its_own_branch_orders(world: World):
    world.create_order()
    assert world.branch_orders("owner")["totalCount"] >= 1
    assert world.branch_orders_error("owner", branch_id=world.other_branch_id).messages
    assert world.branch_orders_error("customer").messages
    assert world.branch_orders("admin")["totalCount"] >= 1


def test_only_admin_sees_the_support_queue(world: World):
    for actor in ("customer", "owner", "courier"):
        assert "Acceso denegado" in str(
            world.client.gql_error(
                "query($jwt: String!) { ordersRequiringAttention(jwt: $jwt) { totalCount } }",
                {"jwt": world.token(actor)},
            )
        ), actor


def test_customer_cannot_rate_before_delivery_or_out_of_range(world: World, order_on_the_way):
    assert "entregados" in str(world.rate_error(order_on_the_way["id"], 5))
    fresh = world.create_order()
    assert world.rate_error(fresh["id"], 5).messages
    assert "entre 1 y 5" in str(world.rate_error(fresh["id"], 6))
