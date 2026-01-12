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
        # Check if APNs is configured
        self.apns_configured = bool(
            settings.apple_team_id and 
            settings.apple_key_id and 
            settings.apple_private_key and
            settings.apple_private_key != "-----BEGIN PRIVATE KEY-----\nTU_LLAVE_AQUI\n-----END PRIVATE KEY-----"
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
        
        # Generate new token
        headers = {
            "alg": "ES256",
            "kid": settings.apple_key_id
        }
        payload = {
            "iss": settings.apple_team_id,
            "iat": int(current_time)
        }
        
        # Handle escaped newlines in private key
        private_key = settings.apple_private_key.replace("\\n", "\n")
        
        self._apns_token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        self._apns_token_time = current_time
        
        return self._apns_token
    
    def _get_apns_url(self) -> str:
        """Get APNs URL based on environment."""
        if settings.environment == "production":
            return self.APNS_PRODUCTION
        return self.APNS_SANDBOX
    
    async def send_to_all(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        platform: str = "IOS"
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple devices.
        
        Args:
            tokens: List of device tokens
            title: Notification title
            body: Notification body
            data: Additional data payload
            platform: "IOS" or "ANDROID"
        
        Returns:
            Dict with success count and failed tokens
        """
        if not tokens:
            return {"success": 0, "failed": 0, "failed_tokens": []}
        
        logger.info(f"Sending push to {len(tokens)} {platform} devices: {title}")
        
        if platform == "IOS":
            return await self._send_apns(tokens, title, body, data)
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
        data: Optional[Dict[str, Any]] = None
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
        
        # Use bundle ID from config (first one if multiple)
        bundle_id = settings.apple_client_id.split(",")[0].strip()
        
        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10"
        }
        
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
                    else:
                        logger.error(f"APNs error for token {token[:10]}...: {response.status_code} - {response.text}")
                        failed_tokens.append(token)
                        
                except Exception as e:
                    logger.error(f"Failed to send to token {token[:10]}...: {e}")
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
    
    Args:
        error_id: The error log ID
        error_type: Type of error
        error_message: Error message (will be truncated)
        severity: Error severity level
    
    Returns:
        Result of push notification attempt
    """
    from repositories.device_token_repository import device_token_repo
    
    # Get all active iOS tokens (admin notification)
    # In production, you might want to filter by admin users
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    if not ios_tokens:
        logger.info("No iOS devices registered for error notifications")
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
    
    return await push_service.send_to_all(
        tokens=ios_tokens,
        title=title,
        body=body,
        data=data,
        platform="IOS"
    )
