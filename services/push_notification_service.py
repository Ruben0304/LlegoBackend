"""Push notification service for APNs and FCM."""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import jwt
from bson import ObjectId
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account as google_service_account

from core.config import settings

logger = logging.getLogger(__name__)

# FCM v1 only accepts scalar string values in the "data" payload.
FCM_MESSAGING_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# Android notification channel the Llego Android app registers for order pushes.
FCM_ANDROID_CHANNEL_ID = "llego_orders"
# FCM error codes (from message.error.details[].errorCode, or top-level
# error.status as a fallback) that mean the token is permanently invalid.
FCM_INVALID_TOKEN_ERROR_CODES = {"UNREGISTERED", "INVALID_ARGUMENT"}


def _normalize_push_payload(value: Any) -> Any:
    """Normalize payload values to JSON-serializable primitives."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize_push_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_push_payload(v) for v in value]
    return value


def _stringify_fcm_data(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Convert a data payload to FCM's required Dict[str, str] shape.

    Reuses the same keys the backend already builds for the order push
    payload (see ``_send_order_status_notification`` in
    ``services/orders_service.py``, e.g. ``type``, ``orderId``); every value
    must become a string for FCM to accept the message.
    """
    if not data:
        return {}
    normalized = _normalize_push_payload(data)
    result: Dict[str, str] = {}
    for key, value in normalized.items():
        if value is None:
            continue
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, bool):
            result[key] = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            result[key] = json.dumps(value)
        else:
            result[key] = str(value)
    return result


def _extract_fcm_error_code(response: httpx.Response) -> Optional[str]:
    """Best-effort extraction of the FCM error code from an error response."""
    try:
        payload = response.json()
    except Exception:
        return None
    error = payload.get("error") or {}
    for detail in error.get("details") or []:
        code = detail.get("errorCode")
        if code:
            return code
    return error.get("status")


class PushNotificationService:
    """Service for sending push notifications to iOS (APNs) and Android (FCM)."""

    # APNs endpoints
    APNS_PRODUCTION = "https://api.push.apple.com"
    APNS_SANDBOX = "https://api.sandbox.push.apple.com"

    # FCM HTTP v1 endpoint template
    FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    def __init__(self):
        # Check if APNs is configured (use dedicated push key or fall back to auth key)
        push_key = settings.apns_private_key or settings.apple_private_key
        push_key_id = settings.apns_key_id or settings.apple_key_id

        self.apns_configured = bool(
            settings.apple_team_id
            and push_key_id
            and push_key
            and push_key
            != "-----BEGIN PRIVATE KEY-----\nTU_LLAVE_AQUI\n-----END PRIVATE KEY-----"
        )

        # APNs JWT token cache
        self._apns_token: Optional[str] = None
        self._apns_token_time: float = 0

        if self.apns_configured:
            logger.info("✓ APNs configured and ready")
        else:
            logger.warning(
                "⚠ APNs not configured - push notifications will be simulated"
            )

        # FCM (Android) configuration - service account credentials loaded from
        # FCM_SERVICE_ACCOUNT_JSON (full JSON content of a Firebase service
        # account key, e.g. a Railway env var). Never log its content.
        self.fcm_configured = False
        self._fcm_project_id: Optional[str] = None
        self._fcm_credentials = None
        self._fcm_token_lock = asyncio.Lock()
        self._init_fcm()

    def _init_fcm(self) -> None:
        """Load FCM service account credentials, if configured."""
        raw_json = settings.fcm_service_account_json
        if not raw_json:
            logger.warning(
                "⚠ FCM not configured (FCM_SERVICE_ACCOUNT_JSON missing) - "
                "Android push notifications will fail explicitly"
            )
            return

        try:
            service_account_info = json.loads(raw_json)
            project_id = service_account_info.get("project_id")
            if not project_id:
                raise ValueError("service account JSON is missing 'project_id'")
            credentials = google_service_account.Credentials.from_service_account_info(
                service_account_info, scopes=[FCM_MESSAGING_SCOPE]
            )
        except Exception as e:
            # Intentionally never log raw_json / service_account_info - only
            # the exception type/message, which do not contain the credential.
            logger.error(
                f"✗ Failed to load FCM service account credentials: "
                f"{type(e).__name__}: {e}"
            )
            return

        self._fcm_project_id = project_id
        self._fcm_credentials = credentials
        self.fcm_configured = True
        logger.info(f"✓ FCM configured and ready (project: {project_id})")

    def _fcm_token_needs_refresh(self) -> bool:
        creds = self._fcm_credentials
        if creds is None:
            return True
        if not creds.valid:
            return True
        if creds.expiry is None:
            return False
        # Refresh a bit before actual expiry to avoid racing against it.
        return (creds.expiry - datetime.utcnow()).total_seconds() < 60

    async def _get_fcm_access_token(self) -> str:
        """Return a valid FCM OAuth2 access token, refreshing if needed.

        google-auth's Credentials.refresh() is synchronous/blocking, so it
        runs in a thread to avoid blocking the event loop.
        """
        async with self._fcm_token_lock:
            if self._fcm_credentials is None:
                raise RuntimeError("FCM credentials not configured")
            if self._fcm_token_needs_refresh():
                await asyncio.to_thread(
                    self._fcm_credentials.refresh, GoogleAuthRequest()
                )
            return self._fcm_credentials.token

    def _get_apns_token(self) -> str:
        """Generate or return cached APNs JWT token (valid for 1 hour)."""
        current_time = time.time()

        # Token valid for 50 minutes (refresh before 1 hour expiry)
        if self._apns_token and (current_time - self._apns_token_time) < 3000:
            return self._apns_token

        # Use dedicated push key or fall back to auth key
        key_id = settings.apns_key_id or settings.apple_key_id
        private_key = settings.apns_private_key or settings.apple_private_key

        # Generate new token
        headers = {"alg": "ES256", "kid": key_id}
        payload = {"iss": settings.apple_team_id, "iat": int(current_time)}

        # Handle escaped newlines in private key
        private_key = private_key.replace("\\n", "\n")

        self._apns_token = jwt.encode(
            payload, private_key, algorithm="ES256", headers=headers
        )
        self._apns_token_time = current_time

        return self._apns_token

    def _get_apns_url(self) -> str:
        """Get APNs URL based on configuration."""
        if settings.apns_use_sandbox:
            return self.APNS_SANDBOX
        return self.APNS_PRODUCTION

    async def send_to_all(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        platform: str = "IOS",
        bundle_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple devices.

        Args:
            tokens: List of device tokens
            title: Notification title
            body: Notification body
            data: Additional data payload
            platform: "IOS" or "ANDROID"
            bundle_id: Optional bundle ID override for APNs

        Returns:
            Dict with success count and failed tokens
        """
        if not tokens:
            return {"success": 0, "failed": 0, "failed_tokens": []}

        logger.info(f"Sending push to {len(tokens)} {platform} devices: {title}")

        if platform == "IOS":
            return await self._send_apns(tokens, title, body, data, bundle_id)
        elif platform == "ANDROID":
            return await self._send_fcm(tokens, title, body, data)
        else:
            logger.error(f"Unknown platform: {platform}")
            return {"success": 0, "failed": len(tokens), "failed_tokens": tokens}

    async def _send_apns(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        bundle_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send push notification via Apple Push Notification service (APNs)."""
        if not self.apns_configured:
            logger.warning("APNs not configured. Notification would be sent:")
            logger.info(f"  Title: {title}")
            logger.info(f"  Body: {body}")
            logger.info(f"  Tokens: {len(tokens)} devices")
            return {
                "success": len(tokens),
                "failed": 0,
                "failed_tokens": [],
                "simulated": True,
            }

        success_count = 0
        failed_tokens = []

        # APNs payload
        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "content-available": 1,
            }
        }
        if data:
            payload["data"] = _normalize_push_payload(data)

        apns_url = self._get_apns_url()
        jwt_token = self._get_apns_token()

        # Use provided bundle_id or default
        topic = (
            bundle_id
            or settings.apns_bundle_id
            or settings.apple_client_id.split(",")[0].strip()
        )

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }

        environment = "SANDBOX" if settings.apns_use_sandbox else "PRODUCTION"
        logger.info(f"📤 Sending to APNs ({environment}): {apns_url}, topic: {topic}")

        async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
            for token in tokens:
                try:
                    url = f"{apns_url}/3/device/{token}"
                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"✅ Push sent successfully to {token[:10]}...")
                    else:
                        error_body = response.text
                        logger.error(
                            f"❌ APNs error {response.status_code} for {token[:10]}...: {error_body}"
                        )
                        failed_tokens.append(token)

                        # Auto-cleanup invalid tokens
                        # APNs status codes that indicate the token should be removed:
                        # 400 BadDeviceToken, 410 Unregistered
                        if response.status_code in [400, 410]:
                            try:
                                from repositories.device_token_repository import (
                                    device_token_repo,
                                )

                                await device_token_repo.deactivate(token)
                                logger.info(
                                    f"🗑️ Auto-removed invalid token {token[:10]}... (status {response.status_code})"
                                )
                            except Exception as cleanup_error:
                                logger.error(
                                    f"Failed to auto-cleanup token: {cleanup_error}"
                                )

                except Exception as e:
                    logger.error(
                        f"❌ Exception sending to {token[:10]}...: {type(e).__name__}: {e}"
                    )
                    failed_tokens.append(token)

        return {
            "success": success_count,
            "failed": len(failed_tokens),
            "failed_tokens": failed_tokens,
        }

    async def _send_fcm(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send push notification via Firebase Cloud Messaging HTTP v1 API.

        Message contract sent to the Android app (do not change without
        coordinating with the Android client):
        {
            "message": {
                "token": "device_token",
                "notification": {"title": "...", "body": "..."},
                "data": { ...same keys the backend builds for the order
                          payload (type, orderId, ...), all values as
                          strings... },
                "android": {
                    "priority": "HIGH",
                    "notification": {"channel_id": "llego_orders"}
                }
            }
        }
        """
        if not self.fcm_configured:
            logger.warning(
                "FCM not configured (FCM_SERVICE_ACCOUNT_JSON missing/invalid). "
                "Notification NOT sent:"
            )
            logger.info(f"  Title: {title}")
            logger.info(f"  Tokens: {len(tokens)} devices")

            return {
                "success": 0,
                "failed": len(tokens),
                "failed_tokens": list(tokens),
                "configured": False,
                "reason": "fcm_not_configured",
            }

        try:
            access_token = await self._get_fcm_access_token()
        except Exception as e:
            logger.error(
                f"❌ Failed to obtain FCM access token: {type(e).__name__}: {e}"
            )
            return {
                "success": 0,
                "failed": len(tokens),
                "failed_tokens": list(tokens),
                "reason": "fcm_auth_failed",
            }

        url = self.FCM_SEND_URL.format(project_id=self._fcm_project_id)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        fcm_data = _stringify_fcm_data(data)

        success_count = 0
        failed_tokens: List[str] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for token in tokens:
                message = {
                    "message": {
                        "token": token,
                        "notification": {"title": title, "body": body},
                        "data": fcm_data,
                        "android": {
                            "priority": "HIGH",
                            "notification": {
                                "channel_id": FCM_ANDROID_CHANNEL_ID,
                            },
                        },
                    }
                }
                try:
                    response = await client.post(url, json=message, headers=headers)

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"✅ FCM push sent successfully to {token[:10]}...")
                    else:
                        error_body = response.text
                        logger.error(
                            f"❌ FCM error {response.status_code} for {token[:10]}...: {error_body}"
                        )
                        failed_tokens.append(token)

                        # Auto-cleanup permanently invalid tokens
                        error_code = _extract_fcm_error_code(response)
                        if (
                            response.status_code in (400, 404)
                            and error_code in FCM_INVALID_TOKEN_ERROR_CODES
                        ):
                            try:
                                from repositories.device_token_repository import (
                                    device_token_repo,
                                )

                                await device_token_repo.deactivate(token)
                                logger.info(
                                    f"🗑️ Auto-removed invalid FCM token {token[:10]}... "
                                    f"(error {error_code})"
                                )
                            except Exception as cleanup_error:
                                logger.error(
                                    f"Failed to auto-cleanup FCM token: {cleanup_error}"
                                )

                except Exception as e:
                    logger.error(
                        f"❌ Exception sending FCM to {token[:10]}...: {type(e).__name__}: {e}"
                    )
                    failed_tokens.append(token)

        return {
            "success": success_count,
            "failed": len(failed_tokens),
            "failed_tokens": failed_tokens,
        }


# Singleton instance
push_service = PushNotificationService()


async def notify_critical_error(
    error_id: str, error_type: str, error_message: str, severity: str = "alta"
) -> Dict[str, Any]:
    """
    Send push notification for critical errors to admin devices.
    """
    from repositories.device_token_repository import device_token_repo

    logger.info(
        f"🔔 notify_critical_error called - severity: {severity}, error_type: {error_type}"
    )

    # Get all active iOS tokens
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]

    logger.info(f"📱 Found {len(ios_tokens)} iOS device tokens")

    if not ios_tokens:
        logger.warning("⚠️ No iOS devices registered for error notifications")
        return {"success": 0, "failed": 0, "no_devices": True}

    # Build notification
    severity_emoji = {"baja": "ℹ️", "media": "⚠️", "alta": "🔴", "critica": "🚨"}
    emoji = severity_emoji.get(severity, "⚠️")

    title = f"{emoji} Error {severity.upper()}: {error_type}"
    body = error_message[:100] + "..." if len(error_message) > 100 else error_message

    data = {"type": "error_alert", "error_id": str(error_id), "severity": severity}

    logger.info(f"📤 Sending push: {title}")

    result = await push_service.send_to_all(
        tokens=ios_tokens, title=title, body=body, data=data, platform="IOS"
    )

    logger.info(f"📬 Push result: {result}")

    return result
