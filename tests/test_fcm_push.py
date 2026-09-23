"""Tests for real FCM (Android) push notification sending.

No real network calls are made: httpx.AsyncClient is mocked out, and the
FCM OAuth2 credentials are mocked/stubbed rather than fetched from Google.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from core.config import settings
from services.push_notification_service import (
    FCM_ANDROID_CHANNEL_ID,
    PushNotificationService,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient supporting `async with`."""

    def __init__(self, responses):
        self.post = AsyncMock(side_effect=list(responses))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _configured_service() -> PushNotificationService:
    """Build a service instance with FCM already 'configured', bypassing
    real credential loading so no network/file access is needed."""
    service = PushNotificationService.__new__(PushNotificationService)
    service.apns_configured = False
    service._apns_token = None
    service._apns_token_time = 0

    service.fcm_configured = True
    service._fcm_project_id = "test-project"

    fake_credentials = MagicMock()
    fake_credentials.valid = True
    fake_credentials.expiry = None
    fake_credentials.token = "fake-access-token"
    service._fcm_credentials = fake_credentials
    service._fcm_token_lock = asyncio.Lock()
    return service


@pytest.mark.asyncio
async def test_send_fcm_builds_well_formed_v1_message():
    """message.token/notification, data as strings, android.priority=HIGH
    and channel_id=llego_orders, per the contract with the Android app."""
    service = _configured_service()
    ok_response = _FakeResponse(200, {"name": "projects/test-project/messages/1"})
    fake_client = _FakeAsyncClient([ok_response])

    data = {
        "orderId": "507f1f77bcf86cd799439011",
        "orderNumber": 42,
        "status": "ACCEPTED",
        "type": "order_status_update",
    }

    with patch(
        "services.push_notification_service.httpx.AsyncClient",
        return_value=fake_client,
    ):
        result = await service._send_fcm(
            tokens=["device-token-1"],
            title="Pedido aceptado",
            body="Tu pedido #42 ha sido aceptado",
            data=data,
        )

    assert result == {"success": 1, "failed": 0, "failed_tokens": []}

    fake_client.post.assert_awaited_once()
    call = fake_client.post.await_args
    assert call.args[0] == (
        "https://fcm.googleapis.com/v1/projects/test-project/messages:send"
    )
    body = call.kwargs["json"]
    message = body["message"]

    assert message["token"] == "device-token-1"
    assert message["notification"] == {
        "title": "Pedido aceptado",
        "body": "Tu pedido #42 ha sido aceptado",
    }
    assert message["android"]["priority"] == "HIGH"
    assert message["android"]["notification"]["channel_id"] == FCM_ANDROID_CHANNEL_ID

    # FCM requires every "data" value to be a string.
    assert message["data"] == {
        "orderId": "507f1f77bcf86cd799439011",
        "orderNumber": "42",
        "status": "ACCEPTED",
        "type": "order_status_update",
    }
    for value in message["data"].values():
        assert isinstance(value, str)

    headers = call.kwargs["headers"]
    assert headers["Authorization"] == "Bearer fake-access-token"


@pytest.mark.asyncio
async def test_send_fcm_not_configured_returns_explicit_failure_and_skips_http():
    """When FCM isn't configured, no HTTP call is made and the result is an
    explicit failure (not a simulated success)."""
    service = PushNotificationService.__new__(PushNotificationService)
    service.fcm_configured = False
    service._fcm_project_id = None
    service._fcm_credentials = None

    with patch(
        "services.push_notification_service.httpx.AsyncClient"
    ) as mock_client_cls:
        result = await service._send_fcm(
            tokens=["t1", "t2"],
            title="Pedido aceptado",
            body="Tu pedido ha sido aceptado",
            data={"type": "order_status_update"},
        )

    mock_client_cls.assert_not_called()
    assert result["success"] == 0
    assert result["failed"] == 2
    assert result["failed_tokens"] == ["t1", "t2"]
    assert result.get("reason") == "fcm_not_configured"
    assert "simulated" not in result


@pytest.mark.asyncio
async def test_send_fcm_unregistered_token_is_deactivated():
    """A 404/UNREGISTERED response deactivates the token via the existing
    device token repository, without failing the whole batch."""
    service = _configured_service()
    error_response = _FakeResponse(
        404,
        {
            "error": {
                "code": 404,
                "message": "Requested entity was not found.",
                "status": "NOT_FOUND",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                        "errorCode": "UNREGISTERED",
                    }
                ],
            }
        },
    )
    fake_client = _FakeAsyncClient([error_response])

    with patch(
        "services.push_notification_service.httpx.AsyncClient",
        return_value=fake_client,
    ), patch(
        "repositories.device_token_repository.device_token_repo.deactivate",
        new_callable=AsyncMock,
    ) as mock_deactivate:
        result = await service._send_fcm(
            tokens=["stale-token"],
            title="Pedido aceptado",
            body="Tu pedido ha sido aceptado",
        )

    assert result["success"] == 0
    assert result["failed"] == 1
    assert result["failed_tokens"] == ["stale-token"]
    mock_deactivate.assert_awaited_once_with("stale-token")


@pytest.mark.asyncio
async def test_send_fcm_other_error_does_not_deactivate_and_reports_failure():
    """A non-invalid-token error (e.g. UNAVAILABLE) fails that token but does
    not deactivate it, and does not stop the rest of the batch."""
    service = _configured_service()
    unavailable = _FakeResponse(
        503,
        {"error": {"code": 503, "status": "UNAVAILABLE", "details": []}},
    )
    ok_response = _FakeResponse(200, {"name": "projects/test-project/messages/2"})
    fake_client = _FakeAsyncClient([unavailable, ok_response])

    with patch(
        "services.push_notification_service.httpx.AsyncClient",
        return_value=fake_client,
    ), patch(
        "repositories.device_token_repository.device_token_repo.deactivate",
        new_callable=AsyncMock,
    ) as mock_deactivate:
        result = await service._send_fcm(
            tokens=["flaky-token", "good-token"],
            title="Pedido aceptado",
            body="Tu pedido ha sido aceptado",
        )

    assert result["success"] == 1
    assert result["failed"] == 1
    assert result["failed_tokens"] == ["flaky-token"]
    mock_deactivate.assert_not_called()


def test_invalid_service_account_json_leaves_fcm_unconfigured():
    """Malformed JSON in FCM_SERVICE_ACCOUNT_JSON must not crash startup and
    must leave fcm_configured False."""
    with patch.object(settings, "fcm_service_account_json", "not-valid-json{"):
        service = PushNotificationService()

    assert service.fcm_configured is False
    assert service._fcm_project_id is None
    assert service._fcm_credentials is None


def test_service_account_json_missing_required_fields_leaves_fcm_unconfigured():
    """Well-formed JSON that isn't a usable service account key (missing the
    private key material, etc.) must also leave fcm_configured False."""
    incomplete_json = json.dumps({"type": "service_account", "project_id": "demo"})

    with patch.object(settings, "fcm_service_account_json", incomplete_json):
        service = PushNotificationService()

    assert service.fcm_configured is False
    assert service._fcm_project_id is None


def test_no_fcm_service_account_json_leaves_fcm_unconfigured():
    """Empty config (the default / unset in Railway) also disables FCM."""
    with patch.object(settings, "fcm_service_account_json", ""):
        service = PushNotificationService()

    assert service.fcm_configured is False
    assert service._fcm_project_id is None
    assert service._fcm_credentials is None
