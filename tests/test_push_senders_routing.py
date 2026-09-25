"""Tests de los puntos que envían pushes: cada uno debe pedir los tokens de su app
(audience) y usar el bundle correcto en APNs. Sin red ni base de datos: el
repositorio de tokens, los repos de negocio y push_service están mockeados.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.orders import OrderStatus
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_CUSTOMER,
    BUSINESS_IOS_BUNDLE_ID,
    device_token_repo,
)
from services.orders_service import OrderService
from services.push_notification_service import notify_critical_error, push_service

OK = {"success": 1, "failed": 0, "failed_tokens": []}


def _tok(value, platform="IOS", user_id=None):
    return SimpleNamespace(token=value, platform=platform, userId=user_id)


def _order(status=OrderStatus.ACCEPTED):
    return SimpleNamespace(
        id="ord-1",
        orderNumber="1042",
        customerId="cust-1",
        branchId="br-1",
        businessId="biz-1",
        total=12.5,
        items=[object()],
        status=status,
    )


# ---------------------------------------------------------------- pedidos


@pytest.mark.asyncio
async def test_customer_order_status_uses_customer_tokens_and_default_bundle():
    get_tokens = AsyncMock(return_value=[_tok("cust-ios"), _tok("cust-android", "ANDROID")])
    send = AsyncMock(return_value=OK)
    with patch.object(device_token_repo, "get_by_user_id", get_tokens), \
         patch.object(push_service, "send_to_all", send):
        await OrderService._send_order_status_notification(None, _order(OrderStatus.ACCEPTED))

    get_tokens.assert_awaited_once_with("cust-1", audience=AUDIENCE_CUSTOMER)
    ios = [c for c in send.await_args_list if c.kwargs["platform"] == "IOS"]
    assert ios[0].kwargs["tokens"] == ["cust-ios"]
    assert ios[0].kwargs.get("bundle_id") is None  # topic por defecto = app de clientes
    assert ios[0].kwargs["data"]["type"] == "order_status_update"


@pytest.mark.asyncio
async def test_new_order_goes_to_business_tokens_with_business_bundle():
    get_tokens = AsyncMock(return_value=[_tok("biz-ios"), _tok("biz-android", "ANDROID")])
    send = AsyncMock(return_value=OK)
    branch = SimpleNamespace(managerIds=["mgr-1"])
    business = SimpleNamespace(id="biz-1", ownerId="owner-1")
    with patch.object(device_token_repo, "get_by_user_id", get_tokens), \
         patch.object(push_service, "send_to_all", send):
        await OrderService._send_new_order_notification_to_business(None, _order(), branch, business)

    assert {c.args[0] for c in get_tokens.await_args_list} == {"owner-1", "mgr-1"}
    assert all(c.kwargs["audience"] == AUDIENCE_BUSINESS for c in get_tokens.await_args_list)
    ios = [c for c in send.await_args_list if c.kwargs["platform"] == "IOS"]
    assert ios and all(c.kwargs["bundle_id"] == BUSINESS_IOS_BUNDLE_ID for c in ios)
    assert ios[0].kwargs["data"]["type"] == "new_order"


@pytest.mark.asyncio
async def test_business_status_update_goes_to_business_tokens_with_business_bundle():
    get_tokens = AsyncMock(return_value=[_tok("biz-ios")])
    send = AsyncMock(return_value=OK)
    with patch("services.orders_service.branches_repo.get_by_id",
               AsyncMock(return_value=SimpleNamespace(managerIds=[]))), \
         patch("services.orders_service.businesses_repo.get_by_id",
               AsyncMock(return_value=SimpleNamespace(ownerId="owner-1"))), \
         patch.object(device_token_repo, "get_by_user_id", get_tokens), \
         patch.object(push_service, "send_to_all", send):
        await OrderService._send_order_status_update_to_business(None, _order(OrderStatus.CANCELLED))

    get_tokens.assert_awaited_once_with("owner-1", audience=AUDIENCE_BUSINESS)
    assert send.await_args.kwargs["bundle_id"] == BUSINESS_IOS_BUNDLE_ID
    assert send.await_args.kwargs["data"]["type"] == "order_status_update_business"


# ---------------------------------------------------------------- KYC


@pytest.mark.asyncio
async def test_kyc_notifies_only_business_app_tokens_of_managers():
    from services.kyc.kyc_notification_service import kyc_notification_service

    get_all = AsyncMock(return_value=[_tok("mgr-biz", user_id="mgr-1"), _tok("other-biz", user_id="x")])
    send = AsyncMock(return_value=OK)
    with patch("services.kyc.kyc_notification_service.branches_repo.get_by_id",
               AsyncMock(return_value=SimpleNamespace(businessId="biz-1", managerIds=["mgr-1"]))), \
         patch("services.kyc.kyc_notification_service.businesses_repo.get_by_id",
               AsyncMock(return_value=SimpleNamespace(ownerId="owner-1"))), \
         patch("services.kyc.kyc_notification_service.kyc_notification_logs_repo.create", AsyncMock()), \
         patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        await kyc_notification_service.notify_merchant(
            kyc_verification_id="kyc-1", branch_id="br-1", event_type="kyc_evaluated",
            title="t", body="b", data={"type": "kyc"},
        )

    get_all.assert_awaited_once_with(audience=AUDIENCE_BUSINESS)
    assert send.await_args.kwargs["tokens"] == ["mgr-biz"]
    assert send.await_args.kwargs["bundle_id"] == BUSINESS_IOS_BUNDLE_ID


# ---------------------------------------------------------------- alertas de errores


@pytest.mark.asyncio
async def test_critical_error_alert_goes_only_to_admins():
    from repositories import users_repo

    get_admin_ids = AsyncMock(return_value=["admin-1"])
    get_tokens = AsyncMock(return_value=[_tok("admin-ios"), _tok("admin-android", "ANDROID")])
    send = AsyncMock(return_value=OK)
    get_all = AsyncMock(side_effect=AssertionError("no debe enviar a todos los tokens"))
    with patch.object(users_repo, "get_ids_by_role", get_admin_ids), \
         patch.object(device_token_repo, "get_by_user_ids", get_tokens), \
         patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        await notify_critical_error("err-1", "ValueError", "boom", "alta")

    get_admin_ids.assert_awaited_once_with("admin")
    get_tokens.assert_awaited_once_with(["admin-1"], audience=AUDIENCE_CUSTOMER)
    assert send.await_args.kwargs["tokens"] == ["admin-ios"]


@pytest.mark.asyncio
async def test_critical_error_alert_without_admins_sends_nothing():
    from repositories import users_repo

    send = AsyncMock(return_value=OK)
    with patch.object(users_repo, "get_ids_by_role", AsyncMock(return_value=[])), \
         patch.object(device_token_repo, "get_by_user_ids", AsyncMock(return_value=[])), \
         patch.object(push_service, "send_to_all", send):
        result = await notify_critical_error("err-1", "ValueError", "boom", "alta")

    assert result.get("no_devices") is True
    send.assert_not_awaited()


# ---------------------------------------------------------------- endpoints manuales


def _push_client():
    from api.endpoints.push_notifications import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_manual_push_clientes_uses_customer_tokens_and_customer_bundle():
    get_all = AsyncMock(return_value=[_tok("cust-ios")])
    send = AsyncMock(return_value=OK)
    with patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        res = _push_client().post("/api/push/clientes", json={"title": "Hola", "body": "Mundo"})

    assert res.status_code == 200, res.text
    get_all.assert_awaited_once_with(audience=AUDIENCE_CUSTOMER)
    assert send.await_args.kwargs["bundle_id"] == "com.ruben.LlegoiOS"


def test_manual_push_negocios_uses_business_tokens_and_business_bundle():
    get_all = AsyncMock(return_value=[_tok("biz-ios")])
    send = AsyncMock(return_value=OK)
    with patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        res = _push_client().post("/api/push/negocios", json={"title": "Hola", "body": "Mundo"})

    assert res.status_code == 200, res.text
    get_all.assert_awaited_once_with(audience=AUDIENCE_BUSINESS)
    assert send.await_args.kwargs["bundle_id"] == BUSINESS_IOS_BUNDLE_ID


def test_manual_push_negocios_without_business_devices_returns_404():
    with patch.object(device_token_repo, "get_all_active", AsyncMock(return_value=[])), \
         patch.object(push_service, "send_to_all", AsyncMock(return_value=OK)) as send:
        res = _push_client().post("/api/push/negocios", json={"title": "Hola", "body": "Mundo"})

    assert res.status_code == 404
    send.assert_not_awaited()


# ---------------------------------------------------------------- endpoints de prueba (admin)


@pytest.mark.parametrize(
    "path,audience,bundle",
    [
        ("/api/error-logs/test-push/clientes", AUDIENCE_CUSTOMER, "com.ruben.LlegoiOS"),
        ("/api/error-logs/test-push/negocios", AUDIENCE_BUSINESS, BUSINESS_IOS_BUNDLE_ID),
    ],
)
def test_admin_test_push_endpoints_route_by_audience(path, audience, bundle):
    from api.endpoints.error_logs import router
    from core.config import settings

    app = FastAPI()
    app.include_router(router)
    get_all = AsyncMock(return_value=[_tok("ios-1")])
    send = AsyncMock(return_value=OK)
    with patch.object(settings, "admin_api_key", "test-admin-key"), \
         patch.object(device_token_repo, "get_all_active", get_all), \
         patch.object(push_service, "send_to_all", send):
        res = TestClient(app).post(path, headers={"Authorization": "Bearer test-admin-key"})

    assert res.status_code == 200, res.text
    get_all.assert_awaited_once_with(audience=audience)
    assert send.await_args.kwargs["bundle_id"] == bundle
