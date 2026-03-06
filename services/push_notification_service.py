"""Push notification service for APNs and FCM."""
from typing import List, Dict, Any, Optional
import httpx
import jwt
import json
import logging
import time
from datetime import datetime

from core.config import settings

logger = logging.getLogger(__name__)


class PushNotificationService:
    """Service for sending push notifications to iOS (APNs) and Android (FCM)."""
    
    # APNs endpoints
    APNS_PRODUCTION = "https://api.push.apple.com"
    APNS_SANDBOX = "https://api.sandbox.push.apple.com"
    
    def __init__(self):
        # Check if APNs is configured (use dedicated push key or fall back to auth key)
        push_key = settings.apns_private_key or settings.apple_private_key
        push_key_id = settings.apns_key_id or settings.apple_key_id
        
        self.apns_configured = bool(
            settings.apple_team_id and 
            push_key_id and 
            push_key and
            push_key != "-----BEGIN PRIVATE KEY-----\nTU_LLAVE_AQUI\n-----END PRIVATE KEY-----"
        )
        self.fcm_configured = False
        
        # APNs JWT token cache
        self._apns_token: Optional[str] = None
        self._apns_token_time: float = 0
        
        if self.apns_configured:
            logger.info("✓ APNs configured and ready")
        else:
            logger.warning("⚠ APNs not configured - push notifications will be simulated")
    
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
        headers = {
            "alg": "ES256",
            "kid": key_id
        }
        payload = {
            "iss": settings.apple_team_id,
            "iat": int(current_time)
        }
        
        # Handle escaped newlines in private key
        private_key = private_key.replace("\\n", "\n")
        
        self._apns_token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
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
        bundle_id: Optional[str] = None
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
        bundle_id: Optional[str] = None
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
                "simulated": True
            }
        
        success_count = 0
        failed_tokens = []
        
        # APNs payload
        payload = {
            "aps": {
                "alert": {
                    "title": title,
                    "body": body
                },
                "sound": "default",
                "content-available": 1
            }
        }
        if data:
            payload["data"] = data
        
        apns_url = self._get_apns_url()
        jwt_token = self._get_apns_token()

        # Use provided bundle_id or default
        topic = bundle_id or settings.apns_bundle_id or settings.apple_client_id.split(",")[0].strip()

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": topic,
            "apns-push-type": "alert",
            "apns-priority": "10"
        }

        environment = "SANDBOX" if settings.apns_use_sandbox else "PRODUCTION"
        logger.info(f"📤 Sending to APNs ({environment}): {apns_url}, topic: {topic}")
        
        async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
            for token in tokens:
                try:
                    url = f"{apns_url}/3/device/{token}"
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"✅ Push sent successfully to {token[:10]}...")
                    else:
                        error_body = response.text
                        logger.error(f"❌ APNs error {response.status_code} for {token[:10]}...: {error_body}")
                        failed_tokens.append(token)

                        # Auto-cleanup invalid tokens
                        # APNs status codes that indicate the token should be removed:
                        # 400 BadDeviceToken, 410 Unregistered
                        if response.status_code in [400, 410]:
                            try:
                                from repositories.device_token_repository import device_token_repo
                                await device_token_repo.deactivate(token)
                                logger.info(f"🗑️ Auto-removed invalid token {token[:10]}... (status {response.status_code})")
                            except Exception as cleanup_error:
                                logger.error(f"Failed to auto-cleanup token: {cleanup_error}")
                        
                except Exception as e:
                    logger.error(f"❌ Exception sending to {token[:10]}...: {type(e).__name__}: {e}")
                    failed_tokens.append(token)
        
        return {
            "success": success_count,
            "failed": len(failed_tokens),
            "failed_tokens": failed_tokens
        }
    
    async def _send_fcm(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send push notification via Firebase Cloud Messaging (FCM).
        
        FCM Payload format:
        {
            "message": {
                "token": "device_token",
                "notification": {
                    "title": "Title",
                    "body": "Body"
                },
                "data": { ... custom data ... },
                "android": {
                    "priority": "high"
                }
            }
        }
        
        TODO: Implement actual FCM integration using:
        - Firebase Admin SDK or HTTP v1 API
        - Service account credentials
        - Proper error handling and retry logic
        
        For now, this logs the notification for testing purposes.
        """
        if not self.fcm_configured:
            logger.warning("FCM not configured. Notification would be sent:")
            logger.info(f"  Title: {title}")
            logger.info(f"  Body: {body}")
            logger.info(f"  Data: {data}")
            logger.info(f"  Tokens: {len(tokens)} devices")
            
            # Simulate success for development
            return {
                "success": len(tokens),
                "failed": 0,
                "failed_tokens": [],
                "simulated": True
            }
        
        # TODO: Implement actual FCM sending
        success_count = 0
        failed_tokens = []
        
        for token in tokens:
            try:
                # Placeholder for actual FCM call
                # await self._send_fcm_single(token, title, body, data)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to token {token[:10]}...: {e}")
                failed_tokens.append(token)
        
        return {
            "success": success_count,
            "failed": len(failed_tokens),
            "failed_tokens": failed_tokens
        }


# Singleton instance
push_service = PushNotificationService()


async def notify_critical_error(
    error_id: str,
    error_type: str,
    error_message: str,
    severity: str = "alta"
) -> Dict[str, Any]:
    """
    Send push notification for critical errors to admin devices.
    """
    from repositories.device_token_repository import device_token_repo
    
    logger.info(f"🔔 notify_critical_error called - severity: {severity}, error_type: {error_type}")
    
    # Get all active iOS tokens
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    logger.info(f"📱 Found {len(ios_tokens)} iOS device tokens")
    
    if not ios_tokens:
        logger.warning("⚠️ No iOS devices registered for error notifications")
        return {"success": 0, "failed": 0, "no_devices": True}
    
    # Build notification
    severity_emoji = {
        "baja": "ℹ️",
        "media": "⚠️", 
        "alta": "🔴",
        "critica": "🚨"
    }
    emoji = severity_emoji.get(severity, "⚠️")
    
    title = f"{emoji} Error {severity.upper()}: {error_type}"
    body = error_message[:100] + "..." if len(error_message) > 100 else error_message
    
    data = {
        "type": "error_alert",
        "error_id": error_id,
        "severity": severity
    }
    
    logger.info(f"📤 Sending push: {title}")
    
    result = await push_service.send_to_all(
        tokens=ios_tokens,
        title=title,
        body=body,
        data=data,
        platform="IOS"
    )
    
    logger.info(f"📬 Push result: {result}")
    
    return result
