"""Acceso a las operaciones de mensajero (services/courier_access.py).

Antes bastaba con estar autenticado: la primera operación de chofer de cualquier
usuario le creaba un registro en `delivery_persons` y ya podía ver pedidos
disponibles, aceptarlos, recogerlos y entregarlos. Ahora hace falta un registro
aprobado (lo crea aprobar una solicitud COURIER del registro de socios) o rol
admin/manager; si no, error cuyo mensaje empieza por "COURIER_NOT_APPROVED".

Los registros anteriores al registro de socios no tienen el campo `approved` y
siguen funcionando (los mensajeros que ya trabajaban no pierden el acceso).

Sin red ni Mongo: repositorios mockeados.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest

import schema.extensions as extensions
import schema.orders.mutations as mutations
import schema.orders.queries as queries
import schema.payments.mutations as payment_mutations
import services.courier_access as courier_access
from core.config import settings
from domain.orders import OrderStatus
from services.courier_access import (
    COURIER_NOT_APPROVED,
    CourierNotApprovedError,
    is_approved_courier,
    require_courier,
)
from services.orders_service import OrderService
from utils.auth import create_access_token

USER_ID = "507f1f77bcf86cd799439015"
COURIER_ID = "507f1f77bcf86cd799439016"
ORDER_ID = "507f1f77bcf86cd799439011"


def run(coro):
    return asyncio.run(coro)


def _courier(approved=None, **extra):
    """Registro de mensajero; approved=None es un registro anterior al campo."""
    fields = {"id": COURIER_ID, "userId": USER_ID, "linkedBranchIds": [], **extra}
    if approved is not None:
        fields["approved"] = approved
    return SimpleNamespace(**fields)


def _info(role=None):
    info = MagicMock()
    info.context = {"user_id": USER_ID if role else None, "user_role": role}
    return info


def _jwt(role="customer"):
    return create_access_token({"user_id": USER_ID, "role": role})


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-courier-access")


@pytest.fixture
def repo(monkeypatch):
    """delivery_persons_repo con un registro configurable por test."""
    state = SimpleNamespace(record=None)
    get_by_user_id = AsyncMock(side_effect=lambda user_id: state.record)
    create = AsyncMock(side_effect=lambda dp: dp)
    dp_repo = courier_access.delivery_persons_repo
    monkeypatch.setattr(dp_repo, "get_by_user_id", get_by_user_id)
    monkeypatch.setattr(dp_repo, "create", create)
    monkeypatch.setattr(
        courier_access.users_repo,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(name="Admin", phone="+5355555555")),
    )
    state.get_by_user_id = get_by_user_id
    state.create = create
    return state


# ------------------------------------------------------------- regla de acceso


@pytest.mark.parametrize(
    "record, expected",
    [
        (None, False),
        (_courier(approved=False), False),
        (_courier(approved=True), True),
        # Registro anterior al registro de socios: sin el campo.
        (_courier(), True),
        (SimpleNamespace(id=COURIER_ID, approved=None), True),
    ],
)
def test_is_approved_courier(record, expected):
    assert is_approved_courier(record) is expected


def test_user_without_record_is_rejected_and_no_record_is_created(repo):
    with pytest.raises(CourierNotApprovedError) as exc:
        run(require_courier(_info("customer"), USER_ID))
    assert str(exc.value).startswith(f"{COURIER_NOT_APPROVED}:")
    assert exc.value.extensions == {"code": COURIER_NOT_APPROVED}
    repo.create.assert_not_awaited()


def test_rejected_courier_is_rejected(repo):
    repo.record = _courier(approved=False)
    with pytest.raises(CourierNotApprovedError):
        run(require_courier(_info("customer"), USER_ID))


@pytest.mark.parametrize("approved", [True, None])
def test_approved_and_legacy_couriers_pass(repo, approved):
    repo.record = _courier(approved=approved)
    assert run(require_courier(_info("customer"), USER_ID)) is repo.record
    repo.create.assert_not_awaited()


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_staff_without_record_gets_one_not_approved(repo, role):
    """admin/manager entran por su rol; su registro nace con approved=False para
    que el acceso dure lo que dure el rol."""
    created = run(require_courier(_info(role), USER_ID))
    repo.create.assert_awaited_once()
    assert created.approved is False
    assert str(created.userId) == USER_ID


def test_staff_with_rejected_record_still_passes(repo):
    repo.record = _courier(approved=False)
    assert run(require_courier(_info("admin"), USER_ID)) is repo.record


def test_risk_admin_is_not_staff_for_couriers(repo):
    with pytest.raises(CourierNotApprovedError):
        run(require_courier(_info("risk_admin"), USER_ID))


# ------------------------------------------------- resolvers de chofer cerrados


def _courier_operations():
    """(nombre, llamada) de las operaciones de chofer, sin datos reales."""
    q = queries.OrderQuery()
    m = mutations.OrderMutation()
    pm = payment_mutations.PaymentMutation()
    from schema.orders.inputs import RequestBranchLinkInput, UpdateDeliveryLocationInput

    return [
        ("availableOrdersForDelivery", lambda info, jwt: q.available_orders_for_delivery(info=info, latitude=23.1, longitude=-82.4, jwt=jwt)),
        ("myCurrentDelivery", lambda info, jwt: q.my_current_delivery(info=info, jwt=jwt)),
        ("myDeliveries", lambda info, jwt: q.my_deliveries(info=info, jwt=jwt)),
        ("myDeliveryStats", lambda info, jwt: q.my_delivery_stats(info=info, jwt=jwt)),
        ("myBranchLinkRequests", lambda info, jwt: q.my_branch_link_requests(info=info, jwt=jwt)),
        ("setDeliveryOnlineStatus", lambda info, jwt: m.set_delivery_online_status(info=info, isOnline=True, jwt=jwt)),
        ("acceptOrderForPayment", lambda info, jwt: m.accept_order_for_payment(info=info, orderId=ORDER_ID, jwt=jwt)),
        ("rejectOrderForPayment", lambda info, jwt: m.reject_order_for_payment(info=info, orderId=ORDER_ID, jwt=jwt)),
        ("acceptDelivery", lambda info, jwt: m.accept_delivery(info=info, orderId=ORDER_ID, jwt=jwt)),
        ("confirmPickup", lambda info, jwt: m.confirm_pickup(info=info, orderId=ORDER_ID, jwt=jwt)),
        ("confirmDelivery", lambda info, jwt: m.confirm_delivery(info=info, orderId=ORDER_ID, deliveryCode="123456", jwt=jwt)),
        ("updateDeliveryLocation", lambda info, jwt: m.update_delivery_location(info=info, input=UpdateDeliveryLocationInput(orderId=ORDER_ID, latitude=23.1, longitude=-82.4), jwt=jwt)),
        ("requestBranchLink", lambda info, jwt: m.request_branch_link(info=info, input=RequestBranchLinkInput(branchId=ORDER_ID, message=None), jwt=jwt)),
        ("cancelBranchLinkRequest", lambda info, jwt: m.cancel_branch_link_request(info=info, requestId=ORDER_ID, jwt=jwt)),
        ("linkVehicle", lambda info, jwt: m.link_vehicle(info=info, vehicle_id=ORDER_ID, jwt=jwt)),
        ("confirmCashReceived", lambda info, jwt: pm.confirm_cash_received(info=info, paymentAttemptId=ORDER_ID, jwt=jwt)),
    ]


@pytest.fixture
def side_effects(monkeypatch):
    """Todo lo que un chofer podría tocar: nada debe llegar a ejecutarse."""
    service = SimpleNamespace(
        accept_order_for_payment=AsyncMock(),
        reject_order_for_payment=AsyncMock(),
        accept_delivery=AsyncMock(),
        confirm_pickup=AsyncMock(),
        confirm_delivery=AsyncMock(),
    )
    monkeypatch.setattr(mutations, "order_service", service)
    payment_service = SimpleNamespace(confirm_cash_received=AsyncMock())
    monkeypatch.setattr(payment_mutations, "payment_service", payment_service)
    monkeypatch.setattr(queries.orders_repo, "get_awaiting_delivery_acceptance_nearby", AsyncMock(return_value=[]))
    monkeypatch.setattr(queries.orders_repo, "get_current_delivery", AsyncMock(return_value=None))
    update_location = AsyncMock()
    monkeypatch.setattr(mutations.delivery_persons_repo, "update_location", update_location)
    monkeypatch.setattr(mutations.delivery_persons_repo, "update_online_status", AsyncMock())
    monkeypatch.setattr(mutations, "_redis_set_courier_presence", lambda *a, **k: None)
    return SimpleNamespace(service=service, payments=payment_service, update_location=update_location)


@pytest.mark.parametrize("name", [name for name, _ in _courier_operations()])
def test_unapproved_user_gets_courier_not_approved(repo, side_effects, name):
    call = dict(_courier_operations())[name]
    info = _info()
    with pytest.raises(Exception) as exc:
        run(call(info, _jwt("customer")))
    assert str(exc.value).startswith(COURIER_NOT_APPROVED), (name, str(exc.value))
    repo.create.assert_not_awaited()
    for method in vars(side_effects.service).values():
        method.assert_not_awaited()
    side_effects.payments.confirm_cash_received.assert_not_awaited()
    side_effects.update_location.assert_not_awaited()


def test_rejected_courier_cannot_take_orders(repo, side_effects):
    repo.record = _courier(approved=False)
    with pytest.raises(Exception, match=COURIER_NOT_APPROVED):
        run(
            mutations.OrderMutation().accept_order_for_payment(
                info=_info(), orderId=ORDER_ID, jwt=_jwt("customer")
            )
        )
    side_effects.service.accept_order_for_payment.assert_not_awaited()


def test_legacy_courier_without_approved_field_keeps_working(repo, side_effects, monkeypatch):
    """Mensajero de antes del registro de socios: su documento no tiene `approved`."""
    repo.record = _courier()
    orders = run(
        queries.OrderQuery().available_orders_for_delivery(
            info=_info(), latitude=23.1, longitude=-82.4, jwt=_jwt("customer")
        )
    )
    assert orders == []

    accepted = SimpleNamespace(id=ORDER_ID)
    side_effects.service.accept_order_for_payment.return_value = accepted
    monkeypatch.setattr(mutations, "order_to_type", lambda order: order)
    result = run(
        mutations.OrderMutation().accept_order_for_payment(
            info=_info(), orderId=ORDER_ID, jwt=_jwt("customer")
        )
    )
    assert result is accepted
    side_effects.service.accept_order_for_payment.assert_awaited_once_with(ORDER_ID, USER_ID)
    repo.create.assert_not_awaited()


def test_admin_can_use_courier_operations(repo, side_effects):
    orders = run(
        queries.OrderQuery().available_orders_for_delivery(
            info=_info(), latitude=23.1, longitude=-82.4, jwt=_jwt("admin")
        )
    )
    assert orders == []
    repo.create.assert_awaited_once()


# ------------------------------------------- el servicio ya no crea registros


def test_order_service_does_not_create_courier_records():
    service = OrderService()
    create = AsyncMock()
    service.delivery_repo = SimpleNamespace(
        get_by_user_id=AsyncMock(return_value=None), create=create
    )
    order = SimpleNamespace(
        id=ORDER_ID,
        status=OrderStatus.AWAITING_DELIVERY_ACCEPTANCE,
        deliveryPersonId=None,
    )
    service.orders_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=order))
    with pytest.raises(CourierNotApprovedError):
        run(service.accept_order_for_payment(ORDER_ID, USER_ID))
    create.assert_not_awaited()


# ----------------------------------------- no se registra como error del backend


def _extension_with_errors(*messages):
    ext = extensions.ErrorLoggingExtension.__new__(extensions.ErrorLoggingExtension)
    errors = [SimpleNamespace(original_error=ValueError(m)) for m in messages]
    ext.execution_context = SimpleNamespace(
        result=SimpleNamespace(errors=errors), context={"request": None}
    )
    return ext


def test_courier_not_approved_is_not_logged_as_backend_error(monkeypatch):
    logged = []

    async def _log(self, error, request, context):
        logged.append(str(error.original_error))

    monkeypatch.setattr(extensions, "is_sandbox", lambda: False)
    monkeypatch.setattr(extensions.ErrorLoggingExtension, "_log_error", _log)

    async def scenario():
        _extension_with_errors(
            CourierNotApprovedError().args[0], "Pedido no encontrado"
        ).on_request_end()
        await asyncio.sleep(0)

    run(scenario())
    assert logged == ["Pedido no encontrado"]
