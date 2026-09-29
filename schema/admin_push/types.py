"""GraphQL types for push notifications sent from the Panel Admin."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import strawberry

from domain.admin_push import AdminPushNotification, AdminPushTarget
from domain.business_types import DeviceToken
from domain.models import User
from repositories.device_token_repository import token_audience
from schema.business_types.types import DevicePlatformEnum


@strawberry.enum
class PushAudienceEnum(Enum):
    CUSTOMER = "customer"  # Llegó (clientes)
    BUSINESS = "business"  # Llegó Negocios


@strawberry.enum
class PushTargetEnum(Enum):
    USERS = "users"
    DEVICES = "devices"
    APP = "app"


@strawberry.input
class PushRecipientsInput:
    target: PushTargetEnum
    userIds: Optional[List[str]] = None
    deviceIds: Optional[List[str]] = None
    # Obligatoria con target APP; con USERS limita a los dispositivos de esa app.
    audience: Optional[PushAudienceEnum] = None
    platform: Optional[DevicePlatformEnum] = None


@strawberry.input
class AdminSendPushInput:
    title: str
    body: str
    recipients: PushRecipientsInput


@strawberry.type
class PushDeviceUserType:
    id: str
    name: str
    email: str
    phone: Optional[str]


@strawberry.type
class PushDeviceType:
    id: str
    platform: DevicePlatformEnum
    audience: PushAudienceEnum
    appVersion: Optional[str]
    osVersion: Optional[str]
    bundleId: Optional[str]
    # Solo el final del token: basta para distinguir dispositivos sin exponerlo.
    tokenSuffix: str
    createdAt: datetime
    updatedAt: datetime
    user: Optional[PushDeviceUserType]


@strawberry.type
class PushDevicesConnectionType:
    rows: List[PushDeviceType]
    totalCount: int
    hasMore: bool


@strawberry.type
class PushAudienceSizeType:
    total: int
    ios: int
    android: int


@strawberry.type
class AdminPushNotificationType:
    id: str
    title: str
    body: str
    target: PushTargetEnum
    audience: Optional[PushAudienceEnum]
    platform: Optional[DevicePlatformEnum]
    userCount: int
    deviceCount: int
    totalDevices: int
    sent: int
    failed: int
    simulated: bool
    sentByName: Optional[str]
    createdAt: datetime


@strawberry.type
class AdminPushHistoryConnectionType:
    rows: List[AdminPushNotificationType]
    totalCount: int
    hasMore: bool


def recipients_to_domain(recipients: PushRecipientsInput) -> dict:
    return {
        "target": AdminPushTarget(recipients.target.value),
        "user_ids": list(dict.fromkeys(recipients.userIds or [])),
        "device_ids": list(dict.fromkeys(recipients.deviceIds or [])),
        "audience": recipients.audience.value if recipients.audience else None,
        "platform": recipients.platform.value if recipients.platform else None,
    }


def device_to_type(device: DeviceToken, users: Dict[str, User]) -> PushDeviceType:
    user = users.get(str(device.userId)) if device.userId else None
    return PushDeviceType(
        id=str(device.id),
        platform=DevicePlatformEnum(device.platform),
        audience=PushAudienceEnum(token_audience(device)),
        appVersion=device.appVersion,
        osVersion=device.osVersion,
        bundleId=device.bundleId,
        tokenSuffix=device.token[-8:],
        createdAt=device.createdAt,
        updatedAt=device.updatedAt,
        user=PushDeviceUserType(
            id=str(user.id), name=user.name, email=user.email, phone=user.phone
        )
        if user
        else None,
    )


def notification_to_type(n: AdminPushNotification) -> AdminPushNotificationType:
    return AdminPushNotificationType(
        id=str(n.id),
        title=n.title,
        body=n.body,
        target=PushTargetEnum(n.target),
        audience=PushAudienceEnum(n.audience) if n.audience else None,
        platform=DevicePlatformEnum(n.platform) if n.platform else None,
        userCount=len(n.userIds),
        deviceCount=len(n.deviceIds),
        totalDevices=n.totalDevices,
        sent=n.sent,
        failed=n.failed,
        simulated=n.simulated,
        sentByName=n.sentByName,
        createdAt=n.createdAt,
    )
