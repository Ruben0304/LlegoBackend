"""Envío de notificaciones push desde el Panel Admin a cuentas, dispositivos o apps."""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bson import ObjectId

from domain.admin_push import AdminPushNotification, AdminPushTarget
from domain.business_types import DeviceToken
from repositories import users_repo
from repositories.admin_push_repository import admin_push_repo
from repositories.device_token_repository import (
    AUDIENCE_BUSINESS,
    AUDIENCE_CUSTOMER,
    device_token_repo,
)
from services.push_notification_service import push_service

MAX_TITLE_LENGTH = 80
MAX_BODY_LENGTH = 500
AUDIENCES = (AUDIENCE_CUSTOMER, AUDIENCE_BUSINESS)

# Las apps ignoran tipos que no conocen: la notificación se muestra y al tocarla
# solo abre la app.
PUSH_TYPE = "admin_message"


def normalize_message(title: str, body: str) -> Tuple[str, str]:
    title = " ".join(title.split())
    body = body.strip()
    if not title:
        raise ValueError("El título es obligatorio")
    if not body:
        raise ValueError("El mensaje es obligatorio")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"El título admite como máximo {MAX_TITLE_LENGTH} caracteres")
    if len(body) > MAX_BODY_LENGTH:
        raise ValueError(f"El mensaje admite como máximo {MAX_BODY_LENGTH} caracteres")
    return title, body


async def resolve_devices(
    target: AdminPushTarget,
    user_ids: List[str],
    device_ids: List[str],
    audience: Optional[str],
    platform: Optional[str],
) -> List[DeviceToken]:
    """Dispositivos activos a los que llegaría el envío, sin tokens repetidos."""
    if audience is not None and audience not in AUDIENCES:
        raise ValueError("App desconocida")

    if target == AdminPushTarget.USERS:
        if not user_ids:
            raise ValueError("Elige al menos una cuenta")
        devices = await device_token_repo.get_by_user_ids(user_ids, audience=audience)
    elif target == AdminPushTarget.DEVICES:
        if not device_ids:
            raise ValueError("Elige al menos un dispositivo")
        devices = await device_token_repo.get_active_by_ids(device_ids)
    else:
        if audience is None:
            raise ValueError("Elige a qué app enviar")
        devices = await device_token_repo.get_all_active(audience=audience)

    if platform:
        devices = [d for d in devices if d.platform == platform]

    unique: Dict[str, DeviceToken] = {}
    for d in devices:
        unique.setdefault(d.token, d)
    return list(unique.values())


def group_for_delivery(
    devices: List[DeviceToken],
) -> Dict[Tuple[str, Optional[str]], List[str]]:
    """Agrupa tokens por (plataforma, bundle de APNs).

    APNs rechaza un token enviado con el topic de otra app, así que cada app de
    iOS va en su propio envío. Sin bundleId es la app de clientes, que usa el
    topic por defecto. FCM no necesita bundle.
    """
    groups: Dict[Tuple[str, Optional[str]], List[str]] = defaultdict(list)
    for d in devices:
        bundle_id = (d.bundleId or None) if d.platform == "IOS" else None
        groups[(d.platform, bundle_id)].append(d.token)
    return dict(groups)


async def send_admin_push(
    *,
    title: str,
    body: str,
    target: AdminPushTarget,
    user_ids: List[str],
    device_ids: List[str],
    audience: Optional[str],
    platform: Optional[str],
    sent_by_id: str,
) -> AdminPushNotification:
    title, body = normalize_message(title, body)
    devices = await resolve_devices(target, user_ids, device_ids, audience, platform)
    if not devices:
        raise ValueError("No hay dispositivos activos para ese destino")

    notification_id = ObjectId()
    data = {"type": PUSH_TYPE, "notificationId": str(notification_id)}

    sent = failed = 0
    simulated = False
    for (device_platform, bundle_id), tokens in group_for_delivery(devices).items():
        result = await push_service.send_to_all(
            tokens=tokens,
            title=title,
            body=body,
            data=data,
            platform=device_platform,
            bundle_id=bundle_id,
        )
        sent += result.get("success", 0)
        failed += result.get("failed", 0)
        simulated = simulated or bool(result.get("simulated"))

    sender = await users_repo.get_by_id(sent_by_id)
    return await admin_push_repo.create(
        {
            "_id": notification_id,
            "title": title,
            "body": body,
            "target": target.value,
            "audience": audience,
            "platform": platform,
            "userIds": list(user_ids) if target == AdminPushTarget.USERS else [],
            "deviceIds": list(device_ids) if target == AdminPushTarget.DEVICES else [],
            "totalDevices": len(devices),
            "sent": sent,
            "failed": failed,
            "simulated": simulated,
            "sentById": sent_by_id,
            "sentByName": sender.name if sender else None,
            "createdAt": datetime.utcnow(),
        }
    )
