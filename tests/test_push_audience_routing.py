"""Tests for routing pushes to the right app (customer vs business) and for
APNs token cleanup only on errors that really mean the token is invalid.

No real network or database access: httpx.AsyncClient and the device token
repository are mocked out.
"""

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from domain.business_types import DeviceToken
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_CUSTOMER,
    _filter_audience,
    token_audience,
)
from services.push_notification_service import PushNotificationService


def _token(value: str, bundle_id=None) -> DeviceToken:
    now = datetime.utcnow()
    return DeviceToken(
        _id="0" * 24,
        token=value,
        platform="IOS",
        bundleId=bundle_id,
        createdAt=now,
        updatedAt=now,
    )


def test_token_without_bundle_id_is_customer():
    assert token_audience(_token("a")) == AUDIENCE_CUSTOMER
    assert token_audience(_token("b", "com.ruben.LlegoiOS")) == AUDIENCE_CUSTOMER


def test_business_bundle_ids_are_business():
    assert token_audience(_token("a", "com.llego.business.LlegoBusiness")) == AUDIENCE_BUSINESS
    assert token_audience(_token("b", "com.llego.business")) == AUDIENCE_BUSINESS


def test_filter_audience_splits_tokens():
    tokens = [
        _token("customer-legacy"),
        _token("customer", "com.ruben.LlegoiOS"),
        _token("business", "com.llego.business.LlegoBusiness"),
    ]
    assert [t.token for t in _filter_audience(tokens, AUDIENCE_CUSTOMER)] == [
        "customer-legacy",
        "customer",
    ]
    assert [t.token for t in _filter_audience(tokens, AUDIENCE_BUSINESS)] == ["business"]
    assert len(_filter_audience(tokens, None)) == 3


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses):
        self.post = AsyncMock(side_effect=list(responses))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _apns_service() -> PushNotificationService:
    service = PushNotificationService.__new__(PushNotificationService)
    service.apns_configured = True
    service.fcm_configured = False
    service._get_apns_token = lambda: "fake-jwt"
    service._get_apns_url = lambda: "https://api.sandbox.push.apple.com"
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,reason,should_deactivate",
    [
        (400, "DeviceTokenNotForTopic", False),
        (400, "BadDeviceToken", True),
        (410, "Unregistered", True),
        (400, "PayloadTooLarge", False),
    ],
)
async def test_apns_cleanup_only_for_invalid_tokens(status_code, reason, should_deactivate):
    service = _apns_service()
    fake_client = _FakeAsyncClient([_FakeResponse(status_code, {"reason": reason})])
    deactivate = AsyncMock(return_value=True)

    with patch("services.push_notification_service.httpx.AsyncClient", return_value=fake_client), patch(
        "repositories.device_token_repository.device_token_repo.deactivate", deactivate
    ):
        result = await service._send_apns(["tok1234567890"], "t", "b", {"type": "x"}, "com.test")

    assert result["failed"] == 1
    assert deactivate.await_count == (1 if should_deactivate else 0)
