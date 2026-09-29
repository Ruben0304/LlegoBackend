"""Notificaciones push desde el Panel Admin: a quién llegan, cómo se reparten entre
APNs/FCM y quién puede enviarlas. Sin red ni base de datos: repos y push_service
mockeados.
"""

import itertools
import os
from datetime import datetime
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

import services.admin_push as admin_push
from domain.admin_push import AdminPushTarget
from domain.business_types import DeviceToken
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_CUSTOMER,
    BUSINESS_IOS_BUNDLE_ID,
    _audience_query,
)
from schema.admin_push.mutations import AdminPushMutation
from schema.admin_push.types import (
    AdminSendPushInput,
    PushRecipientsInput,
    PushTargetEnum,
)
from utils.auth import create_access_token

ADMIN_ID = "507f1f77bcf86cd799439011"
USER_ID = "507f1f77bcf86cd799439012"
OK = {"success": 1, "failed": 0, "failed_tokens": []}
_ids = itertools.count(1)


def _device(token, platform="IOS", bundle_id=None):
    now = datetime(2026, 9, 1)
    return DeviceToken(
        _id=f"507f1f77bcf86cd7994{next(_ids):05d}",
        token=token,
        platform=platform,
        bundleId=bundle_id,
        createdAt=now,
        updatedAt=now,
    )


def _send_kwargs(**overrides):
    kwargs = dict(
        title="Hola",
        body="Tenemos novedades",
        target=AdminPushTarget.APP,
        user_ids=[],
        device_ids=[],
        audience=AUDIENCE_CUSTOMER,
        platform=None,
        sent_by_id=ADMIN_ID,
    )
    kwargs.update(overrides)
    return kwargs


@pytest.fixture
def history():
    create = AsyncMock(side_effect=lambda data: SimpleNamespace(**data))
    with patch.object(admin_push.admin_push_repo, "create", create), patch.object(
        admin_push.users_repo, "get_by_id", AsyncMock(return_value=SimpleNamespace(name="Ana"))
    ):
        yield create


# --- Mensaje ---------------------------------------------------------------------


def test_message_is_trimmed():
    assert admin_push.normalize_message("  Nueva   promo ", "  Hoy  \n") == (
        "Nueva promo",
        "Hoy",
    )


@pytest.mark.parametrize(
    "title,body",
    [("", "x"), ("   ", "x"), ("x", ""), ("x" * 81, "x"), ("x", "x" * 501)],
)
def test_invalid_messages_are_rejected(title, body):
    with pytest.raises(ValueError):
        admin_push.normalize_message(title, body)


# --- Destinatarios ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_users_target_uses_their_devices_and_dedupes_tokens():
    get = AsyncMock(return_value=[_device("t1"), _device("t1"), _device("t2", "ANDROID")])
    with patch.object(admin_push.device_token_repo, "get_by_user_ids", get):
        devices = await admin_push.resolve_devices(
            AdminPushTarget.USERS, [USER_ID], [], AUDIENCE_BUSINESS, None
        )
    get.assert_awaited_once_with([USER_ID], audience=AUDIENCE_BUSINESS)
    assert [d.token for d in devices] == ["t1", "t2"]


@pytest.mark.asyncio
async def test_platform_filter_applies_to_any_target():
    get = AsyncMock(return_value=[_device("t1"), _device("t2", "ANDROID")])
    with patch.object(admin_push.device_token_repo, "get_active_by_ids", get):
        devices = await admin_push.resolve_devices(
            AdminPushTarget.DEVICES, [], ["d1", "d2"], None, "ANDROID"
        )
    assert [d.token for d in devices] == ["t2"]


@pytest.mark.parametrize(
    "target,user_ids,device_ids,audience",
    [
        (AdminPushTarget.USERS, [], [], None),
        (AdminPushTarget.DEVICES, [], [], None),
        (AdminPushTarget.APP, [], [], None),
        (AdminPushTarget.APP, [], [], "couriers"),
    ],
)
@pytest.mark.asyncio
async def test_incomplete_recipients_are_rejected(target, user_ids, device_ids, audience):
    with pytest.raises(ValueError):
        await admin_push.resolve_devices(target, user_ids, device_ids, audience, None)


def test_audience_query_matches_token_audience():
    assert _audience_query(None) == {}
    business = _audience_query(AUDIENCE_BUSINESS)["bundleId"]
    assert business.match(BUSINESS_IOS_BUNDLE_ID)
    customer = _audience_query(AUDIENCE_CUSTOMER)["bundleId"]["$not"]
    assert customer.pattern == business.pattern


# --- Envío -----------------------------------------------------------------------


def test_ios_devices_are_grouped_by_app_bundle():
    groups = admin_push.group_for_delivery(
        [
            _device("c1"),
            _device("b1", bundle_id=BUSINESS_IOS_BUNDLE_ID),
            _device("c2"),
            _device("a1", "ANDROID", bundle_id="com.llego.business"),
        ]
    )
    assert groups == {
        ("IOS", None): ["c1", "c2"],
        ("IOS", BUSINESS_IOS_BUNDLE_ID): ["b1"],
        ("ANDROID", None): ["a1"],
    }


@pytest.mark.asyncio
async def test_send_delivers_each_group_and_saves_history(history):
    devices = [_device("c1"), _device("b1", bundle_id=BUSINESS_IOS_BUNDLE_ID), _device("a1", "ANDROID")]
    send = AsyncMock(return_value=OK)
    with patch.object(admin_push, "resolve_devices", AsyncMock(return_value=devices)), \
         patch.object(admin_push.push_service, "send_to_all", send):
        record = await admin_push.send_admin_push(**_send_kwargs(audience=None, target=AdminPushTarget.DEVICES, device_ids=["x"]))

    calls = {(c.kwargs["platform"], c.kwargs["bundle_id"]): c.kwargs for c in send.await_args_list}
    assert set(calls) == {("IOS", None), ("IOS", BUSINESS_IOS_BUNDLE_ID), ("ANDROID", None)}
    data = calls[("IOS", None)]["data"]
    assert data["type"] == "admin_message"
    assert data["notificationId"] == str(record._id)
    assert (record.totalDevices, record.sent, record.failed) == (3, 3, 0)
    assert record.deviceIds == ["x"] and record.userIds == []
    assert record.sentByName == "Ana"


@pytest.mark.asyncio
async def test_send_without_devices_fails_and_saves_nothing(history):
    with patch.object(admin_push, "resolve_devices", AsyncMock(return_value=[])):
        with pytest.raises(ValueError):
            await admin_push.send_admin_push(**_send_kwargs())
    history.assert_not_awaited()


# --- Permisos --------------------------------------------------------------------


def _input():
    return AdminSendPushInput(
        title="Hola",
        body="Mundo",
        recipients=PushRecipientsInput(target=PushTargetEnum.APP),
    )


@pytest.mark.asyncio
async def test_manager_cannot_send():
    jwt = create_access_token({"user_id": ADMIN_ID, "role": "manager"})
    send = AsyncMock()
    with patch("schema.admin_push.mutations.send_admin_push", send):
        with pytest.raises(Exception, match="Acceso denegado"):
            await AdminPushMutation().admin_send_push(
                info=SimpleNamespace(context={}), input=_input(), jwt=jwt
            )
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_validation_errors_reach_the_panel_as_messages():
    jwt = create_access_token({"user_id": ADMIN_ID, "role": "admin"})
    with pytest.raises(Exception, match="Elige a qué app enviar"):
        await AdminPushMutation().admin_send_push(
            info=SimpleNamespace(context={}), input=_input(), jwt=jwt
        )
