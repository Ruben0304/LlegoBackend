"""Tests del ciclo de vida pedido/pago: casos reales donde el cliente perdia
dinero o pagaba dos veces (ver MUY_IMPORTANTE_RESOLVER.md, secciones A y E).

Usa repositorios en memoria: no requiere MongoDB.
"""

import asyncio
import os
from datetime import datetime, timedelta

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
from bson import ObjectId

import services.orders_service as orders_module
import services.payments_service as payments_module
from domain.orders import (
    DeliveryAddress,
    GeoPoint,
    Order,
    OrderStatus,
    PaymentStatus,
)
from domain.payments import PaymentAttempt, PaymentAttemptStatus
from services.orders_service import OrderService
from services.payments_service import PaymentService

CUSTOMER_ID = str(ObjectId())
BUSINESS_USER_ID = str(ObjectId())
COURIER_USER_ID = str(ObjectId())
COURIER_ID = str(ObjectId())
TRANSFER_METHOD_ID = str(ObjectId())


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeOrderRepo:
    """Imita la semantica de OrderRepository (incluido el compare-and-set)."""

    def __init__(self):
        self.orders = {}

    def add(self, order: Order) -> Order:
        self.orders[str(order.id)] = order
        return order

    def _apply(self, order_id, set_fields, timeline_entry=None):
        data = self.orders[order_id].model_dump(by_alias=True)
        data.update(set_fields)
        if timeline_entry is not None:
            data["timeline"] = data["timeline"] + [timeline_entry.model_dump()]
        self.orders[order_id] = Order.model_validate(data)
        return self.get_copy(order_id)

    def get_copy(self, order_id):
        order = self.orders.get(str(order_id))
        return order.model_copy(deep=True) if order else None

    async def get_by_id(self, order_id):
        return self.get_copy(order_id)

    async def update_status(
        self,
        order_id,
        status,
        timeline_entry,
        extra_set_fields=None,
        expected_status=None,
        require_expired_deadline=False,
    ):
        current = self.orders.get(str(order_id))
        if not current:
            return None
        if expected_status is not None and current.status != expected_status:
            return None
        if require_expired_deadline and (
            current.deadlineAt is None or current.deadlineAt > datetime.utcnow()
        ):
            return None
        fields = {"status": status.value, "updatedAt": datetime.utcnow()}
        fields.update(extra_set_fields or {})
        return self._apply(str(order_id), fields, timeline_entry)

    async def mark_paid(
        self, order_id, attempt_id, from_statuses, new_status, timeline_entry, deadline_at
    ):
        current = self.orders.get(str(order_id))
        if not current or current.status not in from_statuses:
            return None
        return self._apply(
            str(order_id),
            {
                "status": new_status.value,
                "paymentStatus": PaymentStatus.COMPLETED.value,
                "paymentId": attempt_id,
                "paidAt": datetime.utcnow(),
                "deadlineAt": deadline_at,
            },
            timeline_entry,
        )

    async def record_payment(
        self, order_id, attempt_id, attention_reason=None, timeline_entry=None
    ):
        fields = {
            "paymentStatus": PaymentStatus.COMPLETED.value,
            "paymentId": attempt_id,
            "paidAt": datetime.utcnow(),
        }
        if attention_reason:
            fields.update(
                requiresAttention=True,
                attentionReason=attention_reason,
                attentionAt=datetime.utcnow(),
            )
        return self._apply(str(order_id), fields, timeline_entry)

    async def mark_requires_attention(
        self, order_id, reason, timeline_entry=None, expected_status=None, clear_deadline=False
    ):
        current = self.orders.get(str(order_id))
        if not current:
            return None
        if expected_status is not None and current.status != expected_status:
            return None
        fields = {
            "requiresAttention": True,
            "attentionReason": reason,
            "attentionAt": datetime.utcnow(),
        }
        if clear_deadline:
            fields["deadlineAt"] = None
        return self._apply(str(order_id), fields, timeline_entry)

    async def extend_deadline(self, order_id, deadline_at, expected_status):
        current = self.orders.get(str(order_id))
        if not current or current.status != expected_status:
            return None
        if current.deadlineAt is None or current.deadlineAt < deadline_at:
            return self._apply(str(order_id), {"deadlineAt": deadline_at})
        return self.get_copy(order_id)

    async def get_expired_preparation_candidates(self, statuses, now=None, limit=100):
        now = now or datetime.utcnow()
        return [
            o.model_copy(deep=True)
            for o in self.orders.values()
            if o.status in statuses and o.deadlineAt is not None and o.deadlineAt <= now
        ][:limit]

    async def update_delivery_fee(self, order_id, delivery_fee, total, delivery_mode="branch"):
        return self._apply(
            str(order_id),
            {"deliveryFee": delivery_fee, "total": total, "deliveryMode": delivery_mode},
        )


class FakeAttemptRepo:
    FINAL = {"completed", "failed", "expired", "cancelled", "refunded"}
    OPEN = {"pending", "awaiting_proof", "awaiting_kyc", "awaiting_delivery"}

    def __init__(self):
        self.attempts = {}

    def add(self, order_id, status, method_id=TRANSFER_METHOD_ID) -> PaymentAttempt:
        attempt = PaymentAttempt(
            _id=str(ObjectId()),
            orderId=str(order_id),
            paymentMethodId=method_id,
            subtotal=100.0,
            deliveryFee=10.0,
            commissionAmount=0.0,
            totalAmount=110.0,
            currency="local",
            status=status,
        )
        self.attempts[str(attempt.id)] = attempt
        return attempt

    def status_of(self, attempt_id):
        status = self.attempts[str(attempt_id)].status
        return getattr(status, "value", status)

    async def get_by_id(self, attempt_id):
        return self.attempts.get(str(attempt_id))

    async def get_by_order_id(self, order_id):
        return [a for a in self.attempts.values() if str(a.orderId) == str(order_id)]

    async def get_active_by_order_id(self, order_id):
        for attempt in await self.get_by_order_id(order_id):
            if getattr(attempt.status, "value", attempt.status) not in self.FINAL:
                return attempt
        return None

    async def cancel_open_attempts_for_order(self, order_id):
        count = 0
        for attempt in await self.get_by_order_id(order_id):
            if getattr(attempt.status, "value", attempt.status) in self.OPEN:
                attempt.status = PaymentAttemptStatus.CANCELLED.value
                count += 1
        return count

    async def update_status(self, attempt_id, status, **extra):
        attempt = self.attempts[str(attempt_id)]
        attempt.status = status.value
        return attempt

    async def set_proof(self, attempt_id, proof_url=None):
        attempt = self.attempts[str(attempt_id)]
        attempt.status = PaymentAttemptStatus.AWAITING_BUSINESS.value
        attempt.proofUrl = proof_url
        return attempt


class FakeAccessChecker:
    def __init__(self, allowed_user_ids):
        self.allowed = set(allowed_user_ids)

    async def check_branch_access(self, user_id, branch_id, require_owner=False):
        if str(user_id) in self.allowed:
            return True, None
        return False, "No tienes acceso a esta sucursal"


class FakeDeliveryRepo:
    class _DP:
        id = COURIER_ID

    async def get_by_user_id(self, user_id):
        return self._DP() if str(user_id) == COURIER_USER_ID else None

    async def complete_delivery(self, delivery_person_id):
        return None


@pytest.fixture
def env(monkeypatch):
    order_repo = FakeOrderRepo()
    attempt_repo = FakeAttemptRepo()
    access = FakeAccessChecker({BUSINESS_USER_ID})

    service = OrderService()
    service.orders_repo = order_repo
    service.delivery_repo = FakeDeliveryRepo()

    async def _no_emit(order):
        return None

    service._emit_tracking_event = _no_emit
    monkeypatch.setattr(orders_module, "payment_attempts_repo", attempt_repo)
    monkeypatch.setattr(orders_module, "access_checker", access)
    monkeypatch.setattr(orders_module, "order_service", service)
    monkeypatch.setattr(payments_module, "access_checker", access)

    payments = PaymentService()
    payments.payment_attempts_repo = attempt_repo

    async def _get_order(order_id):
        order = order_repo.get_copy(order_id)
        if not order:
            return None
        doc = order.model_dump(by_alias=True)
        doc["_id"] = order.id
        return doc

    async def _noop(*args, **kwargs):
        return None

    payments._get_order = _get_order
    payments._update_order_payment_attempt = _noop

    return {
        "service": service,
        "payments": payments,
        "orders": order_repo,
        "attempts": attempt_repo,
    }


def make_order(status, *, payment_status=PaymentStatus.PENDING, deadline_in_minutes=-1, **extra):
    now = datetime.utcnow()
    return Order(
        _id=str(ObjectId()),
        orderNumber=f"TST-{ObjectId()}",
        customerId=CUSTOMER_ID,
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
            street="Calle 23", coordinates=GeoPoint(coordinates=[-82.38, 23.13])
        ),
        paymentMethod="transfer",
        paymentStatus=payment_status,
        deadlineAt=now + timedelta(minutes=deadline_in_minutes)
        if deadline_in_minutes is not None
        else None,
        createdAt=now,
        updatedAt=now,
        lastStatusAt=now,
        **extra,
    )


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A1 / A2 — el worker de timeouts nunca cancela pedidos con dinero de por medio
# ---------------------------------------------------------------------------


def test_timeout_cancels_unpaid_order_and_its_open_attempt(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    cancelled = run(env["service"].expire_stale_pre_preparation_orders())

    assert cancelled == 1
    assert env["orders"].get_copy(order.id).status == OrderStatus.CANCELLED
    # El cliente ya no puede "confirmar pago enviado" sobre un pedido cancelado.
    assert env["attempts"].status_of(attempt.id) == "cancelled"


def test_timeout_escalates_instead_of_cancelling_when_payment_was_sent(env):
    order = env["orders"].add(make_order(OrderStatus.PAYMENT_IN_PROGRESS))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_BUSINESS)

    cancelled = run(env["service"].expire_stale_pre_preparation_orders())

    stored = env["orders"].get_copy(order.id)
    assert cancelled == 0
    assert stored.status == OrderStatus.PAYMENT_IN_PROGRESS
    assert stored.requiresAttention is True
    assert stored.deadlineAt is None  # el worker no lo vuelve a procesar
    assert env["attempts"].status_of(attempt.id) == "awaiting_business"


def test_timeout_escalates_paid_order_that_business_did_not_start(env):
    order = env["orders"].add(
        make_order(OrderStatus.ACCEPTED, payment_status=PaymentStatus.COMPLETED)
    )

    cancelled = run(env["service"].expire_stale_pre_preparation_orders())

    stored = env["orders"].get_copy(order.id)
    assert cancelled == 0
    assert stored.status == OrderStatus.ACCEPTED
    assert stored.requiresAttention is True


def test_payment_confirmation_resets_deadline(env):
    # El deadline viejo de la etapa de pago ya habia vencido.
    order = env["orders"].add(make_order(OrderStatus.PAYMENT_IN_PROGRESS))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.COMPLETED)

    run(env["service"].mark_order_paid(str(order.id), str(attempt.id)))

    stored = env["orders"].get_copy(order.id)
    assert stored.status == OrderStatus.ACCEPTED
    assert stored.paymentStatus == PaymentStatus.COMPLETED
    assert stored.deadlineAt > datetime.utcnow() + timedelta(minutes=15)
    # Y el worker ya no lo toca.
    assert run(env["service"].expire_stale_pre_preparation_orders()) == 0
    assert env["orders"].get_copy(order.id).status == OrderStatus.ACCEPTED


def test_late_payment_on_cancelled_order_is_flagged_not_revived(env):
    order = env["orders"].add(make_order(OrderStatus.CANCELLED, deadline_in_minutes=None))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.COMPLETED)

    run(env["service"].mark_order_paid(str(order.id), str(attempt.id)))

    stored = env["orders"].get_copy(order.id)
    assert stored.status == OrderStatus.CANCELLED
    assert stored.paymentStatus == PaymentStatus.COMPLETED
    assert stored.requiresAttention is True


def test_admin_cancel_with_payment_sent_flags_for_refund(env):
    order = env["orders"].add(make_order(OrderStatus.PAYMENT_IN_PROGRESS))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_BUSINESS)

    run(
        env["service"].update_status(
            str(order.id), OrderStatus.CANCELLED, orders_module.OrderActor.SYSTEM
        )
    )

    stored = env["orders"].get_copy(order.id)
    assert stored.status == OrderStatus.CANCELLED
    assert stored.requiresAttention is True
    # El intento con dinero declarado no se toca: lo resuelve una persona.
    assert env["attempts"].status_of(attempt.id) == "awaiting_business"


# ---------------------------------------------------------------------------
# E4 — compare-and-set: una lectura vieja no pisa un cambio concurrente
# ---------------------------------------------------------------------------


def test_stale_status_update_does_not_overwrite_concurrent_payment(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    stale_copy = env["orders"].get_copy(order.id)

    # En paralelo el negocio confirma el pago...
    run(env["service"].mark_order_paid(str(order.id), str(ObjectId())))

    # ...y el worker, con su lectura vieja, intenta cancelar.
    async def stale_get(order_id):
        return stale_copy

    env["service"].orders_repo.get_by_id = stale_get
    with pytest.raises(ValueError):
        run(
            env["service"].update_status(
                str(order.id), OrderStatus.CANCELLED, orders_module.OrderActor.SYSTEM
            )
        )
    assert env["orders"].get_copy(order.id).status == OrderStatus.ACCEPTED


def test_timeout_does_not_cancel_order_accepted_in_parallel(env):
    """Carrera encontrada por la suite E2E: el worker evaluo PENDING_ACCEPTANCE
    vencido, la tienda acepto en paralelo, y el worker cancelaba el pedido ya
    aceptado porque AWAITING_DELIVERY_ACCEPTANCE -> CANCELLED es valido."""
    order = env["orders"].add(make_order(OrderStatus.PENDING_ACCEPTANCE))
    stale_candidate = env["orders"].get_copy(order.id)

    run(
        env["orders"].update_status(
            str(order.id),
            OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
            orders_module.OrderTimeline(
                status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
                timestamp=datetime.utcnow(),
                message="aceptado",
                actor=orders_module.OrderActor.BUSINESS,
            ),
            extra_set_fields={"deadlineAt": datetime.utcnow() + timedelta(minutes=15)},
        )
    )

    assert run(env["service"].expire_order(stale_candidate)) == "skipped"
    assert env["orders"].get_copy(order.id).status == OrderStatus.AWAITING_DELIVERY_ACCEPTANCE


def test_timeout_does_not_cancel_when_deadline_was_just_extended(env):
    """El cliente pulsa "Pagar" (plazo extendido) justo cuando el worker vence."""
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    stale_candidate = env["orders"].get_copy(order.id)
    run(env["service"].extend_payment_deadline(str(order.id)))

    assert run(env["service"].expire_order(stale_candidate)) == "skipped"
    assert env["orders"].get_copy(order.id).status == OrderStatus.PENDING_PAYMENT


# ---------------------------------------------------------------------------
# A6 — con el pago en curso no se cambia el monto ni se rehace el pedido
# ---------------------------------------------------------------------------


def test_business_cannot_modify_items_after_customer_started_paying(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    with pytest.raises(ValueError, match="No se puede modificar"):
        run(
            env["service"].modify_order_items(
                str(order.id), [], "sin stock", BUSINESS_USER_ID
            )
        )


def test_business_cannot_modify_paid_order(env):
    order = env["orders"].add(
        make_order(OrderStatus.ACCEPTED, payment_status=PaymentStatus.COMPLETED)
    )

    with pytest.raises(ValueError, match="No se puede modificar"):
        run(
            env["service"].modify_order_items(
                str(order.id), [], "sin stock", BUSINESS_USER_ID
            )
        )


def test_courier_cannot_release_order_while_customer_is_paying(env):
    order = env["orders"].add(
        make_order(OrderStatus.PENDING_PAYMENT, deliveryPersonId=COURIER_ID)
    )
    env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    with pytest.raises(ValueError, match="No puedes soltar"):
        run(env["service"].reject_order_for_payment(str(order.id), COURIER_USER_ID))


def test_customer_cannot_resubmit_while_paying(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    with pytest.raises(ValueError, match="No se puede reenviar"):
        run(env["service"].resubmit_order(str(order.id), CUSTOMER_ID))


def test_accept_with_fee_override_on_non_pending_order_does_not_touch_money(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))

    with pytest.raises(ValueError, match="ya no esta pendiente"):
        run(
            env["service"].accept_order(
                str(order.id), 20, BUSINESS_USER_ID, delivery_fee_override=999.0
            )
        )
    stored = env["orders"].get_copy(order.id)
    assert stored.deliveryFee == 10.0
    assert stored.total == 120.0


# ---------------------------------------------------------------------------
# Cancelacion por el cliente: permitida sin dinero, bloqueada con dinero
# ---------------------------------------------------------------------------


def test_customer_can_cancel_while_waiting_for_store(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_ACCEPTANCE))

    run(env["service"].cancel_order(str(order.id), CUSTOMER_ID))

    assert env["orders"].get_copy(order.id).status == OrderStatus.CANCELLED


def test_customer_cannot_cancel_after_sending_payment(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_BUSINESS)

    with pytest.raises(ValueError, match="No se puede cancelar"):
        run(env["service"].cancel_order(str(order.id), CUSTOMER_ID))


# ---------------------------------------------------------------------------
# A3 / A5 — reintentos del cliente al pagar
# ---------------------------------------------------------------------------


def test_initiate_payment_reuses_active_attempt(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    existing = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    attempt = run(
        env["payments"].initiate_payment(str(order.id), TRANSFER_METHOD_ID, CUSTOMER_ID)
    )

    assert str(attempt.id) == str(existing.id)


def test_initiate_payment_after_payment_sent_explains_instead_of_generic_error(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_BUSINESS)

    with pytest.raises(ValueError, match="Ya enviaste el pago"):
        run(
            env["payments"].initiate_payment(
                str(order.id), TRANSFER_METHOD_ID, CUSTOMER_ID
            )
        )


def test_payment_sent_moves_order_to_payment_in_progress(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    run(env["payments"].confirm_payment_sent(str(attempt.id), CUSTOMER_ID, None))

    stored = env["orders"].get_copy(order.id)
    assert stored.status == OrderStatus.PAYMENT_IN_PROGRESS
    assert stored.deadlineAt > datetime.utcnow() + timedelta(minutes=25)
    assert env["attempts"].status_of(attempt.id) == "awaiting_business"


def test_payment_sent_retry_is_idempotent(env):
    order = env["orders"].add(make_order(OrderStatus.PENDING_PAYMENT))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    run(env["payments"].confirm_payment_sent(str(attempt.id), CUSTOMER_ID, None))
    # La respuesta se perdio y la app reintenta.
    again = run(env["payments"].confirm_payment_sent(str(attempt.id), CUSTOMER_ID, None))

    assert getattr(again.status, "value", again.status) == "awaiting_business"


def test_payment_sent_on_cancelled_order_is_rejected(env):
    order = env["orders"].add(make_order(OrderStatus.CANCELLED, deadline_in_minutes=None))
    attempt = env["attempts"].add(order.id, PaymentAttemptStatus.AWAITING_PROOF)

    with pytest.raises(ValueError, match="ya no está esperando el pago"):
        run(env["payments"].confirm_payment_sent(str(attempt.id), CUSTOMER_ID, None))
    assert env["attempts"].status_of(attempt.id) == "awaiting_proof"


# ---------------------------------------------------------------------------
# E1 / E2 — permisos
# ---------------------------------------------------------------------------


def test_only_participants_can_view_an_order(env):
    order = env["orders"].add(
        make_order(OrderStatus.ON_THE_WAY, deliveryPersonId=COURIER_ID)
    )
    can = env["service"].user_can_access_order

    assert run(can(order, CUSTOMER_ID))
    assert run(can(order, BUSINESS_USER_ID))
    assert run(can(order, COURIER_USER_ID))
    assert run(can(order, str(ObjectId()), "admin"))
    assert not run(can(order, str(ObjectId())))
    assert not run(can(order, str(ObjectId()), "customer"))
