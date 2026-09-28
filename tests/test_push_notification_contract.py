"""Contracts and routing for notification senders without Mongo or credentials."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from core.config import settings
from domain.payments import PaymentAttemptStatus
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_CUSTOMER,
    BUSINESS_IOS_BUNDLE_ID,
    device_token_repo,
)
from schema.business_types.mutations import BusinessTypeMutation
from schema.business_types.types import (
    CameraConfigInput,
    CreateBusinessTypeConfigInput,
    GradientConfigInput,
    UpdateBusinessTypeConfigInput,
)
from services.payments_service import PaymentService
from services.push_notification_service import (
    FCM_ANDROID_CHANNEL_ID,
    PushNotificationService,
)

OK = {"success": 1, "failed": 0, "failed_tokens": []}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, side_effect):
        self.post = AsyncMock(side_effect=side_effect)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _token(token, platform="IOS", user_id=None):
    return SimpleNamespace(token=token, platform=platform, userId=user_id)


def _service():
    svc = PushNotificationService.__new__(PushNotificationService)
    svc.apns_configured = False
    svc._apns_token = None
    svc._apns_token_time = 0
    svc.fcm_configured = True
    svc._fcm_project_id = "push-test"
    svc._fcm_credentials = SimpleNamespace(
        valid=True, expiry=None, token="access-token"
    )
    svc._fcm_token_lock = asyncio.Lock()
    return svc


@pytest.mark.asyncio
async def test_payment_proof_push_routes_to_business_app_with_expected_payload():
    service = PaymentService()
    service.payment_attempts_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(
            orderId="order-1", status=PaymentAttemptStatus.AWAITING_PROOF
        )),
        set_proof=AsyncMock(return_value="updated"),
    )
    service._get_order = AsyncMock(return_value={
        "customerId": "customer-1", "branchId": "branch-1",
        "orderNumber": 27, "status": "pending_payment",
    })
    service._get_branch = AsyncMock(return_value={
        "businessId": "business-1", "managerIds": ["manager-1"]
    })
    tokens = AsyncMock(side_effect=[[_token("owner-ios")], [_token("manager-android", "ANDROID")]])
    send = AsyncMock(return_value=OK)

    with patch("services.orders_service.order_service.mark_payment_sent", AsyncMock()), \
         patch("repositories.businesses_repo.get_by_id", AsyncMock(return_value=SimpleNamespace(ownerId="owner-1"))), \
         patch.object(device_token_repo, "get_by_user_id", tokens), \
         patch("services.push_notification_service.push_service.send_to_all", send):
        result = await service.confirm_payment_sent("attempt-1", "customer-1", " proof.png ")

    assert result == "updated"
    assert {call.args[0] for call in tokens.await_args_list} == {"owner-1", "manager-1"}
    assert all(call.kwargs["audience"] == AUDIENCE_BUSINESS for call in tokens.await_args_list)
    ios = next(call for call in send.await_args_list if call.kwargs["platform"] == "IOS")
    android = next(call for call in send.await_args_list if call.kwargs["platform"] == "ANDROID")
    assert ios.kwargs["bundle_id"] == BUSINESS_IOS_BUNDLE_ID
    assert ios.kwargs["data"] == android.kwargs["data"] == {
        "orderId": "order-1", "orderNumber": "27", "type": "payment_proof_submitted"
    }


@pytest.mark.asyncio
async def test_business_payment_confirmation_routes_to_customer_with_order_id():
    service = PaymentService()
    service.payment_attempts_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(
            orderId="order-2", status=PaymentAttemptStatus.AWAITING_BUSINESS
        )),
        confirm_business_received=AsyncMock(return_value="confirmed"),
    )
    service._get_order = AsyncMock(return_value={
        "customerId": "customer-2", "branchId": "branch-2", "orderNumber": 42
    })
    service._complete_order_payment = AsyncMock()
    get_tokens = AsyncMock(return_value=[_token("customer-ios"), _token("customer-android", "ANDROID")])
    send = AsyncMock(return_value=OK)
    with patch("services.access_checker.access_checker.check_branch_access", AsyncMock(return_value=(True, None))), \
         patch.object(device_token_repo, "get_by_user_id", get_tokens), \
         patch("services.push_notification_service.push_service.send_to_all", send):
        result = await service.confirm_payment_received("attempt-2", "business-user")

    assert result == "confirmed"
    get_tokens.assert_awaited_once_with("customer-2", audience=AUDIENCE_CUSTOMER)
    assert {call.kwargs["platform"] for call in send.await_args_list} == {"IOS", "ANDROID"}
    for call in send.await_args_list:
        assert call.kwargs.get("bundle_id") is None
        assert call.kwargs["data"] == {
            "orderId": "order-2", "orderNumber": "42", "type": "payment_confirmed_by_business"
        }


@pytest.mark.asyncio
async def test_payment_confirmation_survives_push_sender_exception():
    service = PaymentService()
    service.payment_attempts_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(
            orderId="order-3", status=PaymentAttemptStatus.AWAITING_BUSINESS
        )),
        confirm_business_received=AsyncMock(return_value="confirmed"),
    )
    service._get_order = AsyncMock(return_value={
        "customerId": "customer-3", "branchId": "branch-3", "orderNumber": 43
    })
    service._complete_order_payment = AsyncMock()
    send = AsyncMock(side_effect=TimeoutError("push timeout"))
    with patch("services.access_checker.access_checker.check_branch_access", AsyncMock(return_value=(True, None))), \
         patch.object(device_token_repo, "get_by_user_id", AsyncMock(return_value=[_token("customer-ios")])), \
         patch("services.push_notification_service.push_service.send_to_all", send):
        result = await service.confirm_payment_received("attempt-3", "business-user")

    assert result == "confirmed"
    service.payment_attempts_repo.confirm_business_received.assert_awaited_once_with("attempt-3")
    service._complete_order_payment.assert_awaited_once_with("order-3", "attempt-3")


@pytest.mark.asyncio
async def test_business_type_mutation_pushes_route_to_customer_audience():
    from repositories.business_type_repository import business_type_repo

    now = datetime.now(timezone.utc)
    config = SimpleNamespace(
        id="bt-1", key="sushi", name="Sushi", description="", icon="🍣",
        model3dFileName="", model3dUrl=None, model3dVersion=1,
        gradient=SimpleNamespace(darkColor="#1", mediumColor="#2", lightColor="#3", veryLightColor="#4", overlayColor="#5"),
        camera=SimpleNamespace(positionX=0, positionY=0, positionZ=1, eulerX=0, eulerY=0, eulerZ=0),
        glowColor="#fff", features=[], sortOrder=1, isActive=True,
        createdAt=now, updatedAt=now,
    )
    all_tokens = AsyncMock(return_value=[_token("customer-ios"), _token("customer-android", "ANDROID")])
    send = AsyncMock(return_value=OK)
    gradient = GradientConfigInput(
        dark_color="#1", medium_color="#2", light_color="#3",
        very_light_color="#4", overlay_color="#5",
    )
    camera = CameraConfigInput(position_x=0, position_y=0, position_z=1)
    create_input = CreateBusinessTypeConfigInput(
        key="sushi", name="Sushi", description="", icon="🍣", model3d_file_name="",
        model3d_url=None, gradient=gradient, camera=camera, glow_color="#fff",
        features=[], sort_order=1,
    )
    update_input = UpdateBusinessTypeConfigInput(name="Sushi actualizado")

    with patch("schema.business_types.mutations.require_role"), \
         patch.object(business_type_repo, "create", AsyncMock(return_value=config)), \
         patch.object(business_type_repo, "get_by_id", AsyncMock(return_value=config)), \
         patch.object(business_type_repo, "update", AsyncMock(return_value=config)), \
         patch.object(device_token_repo, "get_all_active", all_tokens), \
         patch("schema.business_types.mutations.push_service.send_to_all", send):
        mutation = BusinessTypeMutation()
        await mutation.create_business_type_config(None, create_input, "jwt")
        await mutation.update_business_type_config(None, "bt-1", update_input, "jwt")

    assert all(call.kwargs == {"audience": AUDIENCE_CUSTOMER} for call in all_tokens.await_args_list)
    assert send.await_count == 4
    for call in send.await_args_list:
        if call.args[-1] == "IOS":
            assert len(call.args[0]) == 1
        assert call.args[-1] in {"IOS", "ANDROID"}
        assert call.args[3]["type"] in {"NEW_BUSINESS_TYPE", "UPDATED_BUSINESS_TYPE"}


@pytest.mark.asyncio
async def test_scheduled_manual_push_uses_requested_bundle_after_delay():
    from api.endpoints.push_notifications import _send_push_delayed
    from repositories.device_token_repository import BUSINESS_IOS_BUNDLE_ID

    send = AsyncMock(return_value=OK)
    with patch("api.endpoints.push_notifications.asyncio.sleep", AsyncMock()), \
         patch("api.endpoints.push_notifications.push_service.send_to_all", send):
        await _send_push_delayed(
            ["business-ios"], "title", "body", BUSINESS_IOS_BUNDLE_ID,
            {"type": "scheduled"}, 30,
        )

    send.assert_awaited_once_with(
        tokens=["business-ios"], title="title", body="body",
        data={"type": "scheduled"}, platform="IOS",
        bundle_id=BUSINESS_IOS_BUNDLE_ID,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,required_keys",
    [
        ({"type": "order_status_update", "orderId": "o1", "status": "ACCEPTED"}, {"type", "orderId", "status"}),
        ({"type": "payment_confirmed_by_business", "orderId": "o1", "orderNumber": "42"}, {"type", "orderId"}),
        ({"type": "new_order", "orderId": "o1", "status": "PENDING"}, {"type", "orderId", "status"}),
        ({"type": "order_status_update_business", "orderId": "o1", "status": "CANCELLED"}, {"type", "orderId", "status"}),
        ({"type": "cash_kyc_status", "payment_attempt_id": "a1", "verification_id": "v1", "kyc_eval_status": "valid"}, {"type", "payment_attempt_id", "verification_id", "kyc_eval_status"}),
        ({"type": "error_alert", "error_id": "e1", "severity": "alta"}, {"type", "error_id", "severity"}),
    ],
)
async def test_fcm_notification_type_payload_contract(payload, required_keys):
    client = FakeClient([FakeResponse(200, {"name": "msg"})])
    with patch("services.push_notification_service.httpx.AsyncClient", return_value=client):
        result = await _service()._send_fcm(["device"], "title", "body", payload)

    assert result["success"] == 1
    message = client.post.await_args.kwargs["json"]["message"]
    assert required_keys <= message["data"].keys()
    assert message["data"]["type"] == payload["type"]
    assert all(isinstance(value, str) for value in message["data"].values())
    assert message["android"]["notification"]["channel_id"] == FCM_ANDROID_CHANNEL_ID == "llego_orders"


def test_apns_jwt_is_signed_es256_and_cached_until_refresh_window():
    private_key = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    service = PushNotificationService.__new__(PushNotificationService)
    service._apns_token = None
    service._apns_token_time = 0
    with patch.object(settings, "apple_team_id", "TEAM123"), \
         patch.object(settings, "apns_key_id", "KEY123"), \
         patch.object(settings, "apple_key_id", ""), \
         patch.object(settings, "apns_private_key", private_key), \
         patch.object(settings, "apple_private_key", ""), \
         patch("services.push_notification_service.time.time", side_effect=[10000, 11000, 14001]):
        first = service._get_apns_token()
        second = service._get_apns_token()
        third = service._get_apns_token()

    header = jwt.get_unverified_header(first)
    claims = jwt.decode(first, private_key, algorithms=["ES256"])
    assert header == {"alg": "ES256", "kid": "KEY123", "typ": "JWT"}
    assert claims == {"iss": "TEAM123", "iat": 10000}
    assert second == first
    assert third != first


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["ANDROID", "IOS"])
async def test_network_timeout_fails_token_without_deactivation(platform):
    service = _service()
    if platform == "IOS":
        service.apns_configured = True
        service._get_apns_token = lambda: "test.jwt"
        service._get_apns_url = lambda: "https://api.sandbox.push.apple.com"
    client = FakeClient([TimeoutError("network timeout")])
    deactivate = AsyncMock()
    with patch("services.push_notification_service.httpx.AsyncClient", return_value=client), \
         patch("repositories.device_token_repository.device_token_repo.deactivate", deactivate):
        result = await service.send_to_all(["token"], "title", "body", {"type": "error_alert"}, platform)

    assert result["success"] == 0
    assert result["failed_tokens"] == ["token"]
    deactivate.assert_not_awaited()
