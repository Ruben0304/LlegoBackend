"""REST endpoints for device token registration (push notifications)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from repositories.device_token_repository import device_token_repo

router = APIRouter(prefix="/api/device-tokens", tags=["Device Tokens"])


@router.get("/")
async def list_device_tokens():
    """List all registered device tokens (for debugging)."""
    tokens = await device_token_repo.get_all_active()
    return {
        "total": len(tokens),
        "tokens": [
            {
                "id": t.id,
                "token_preview": t.token[:20] + "...",
                "platform": t.platform,
                "app_version": t.appVersion,
                "created_at": t.createdAt.isoformat() if t.createdAt else None
            }
            for t in tokens
        ]
    }


class RegisterTokenRequest(BaseModel):
    """Request to register a device token for push notifications."""
    token: str
    platform: Literal["IOS", "ANDROID"] = "IOS"
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None


class RegisterTokenResponse(BaseModel):
    """Response after registering device token."""
    success: bool
    message: str


@router.post("/register", response_model=RegisterTokenResponse)
async def register_device_token(data: RegisterTokenRequest):
    """
    Register a device token for push notifications.
    
    Call this endpoint when:
    - User grants notification permission for the first time
    - App launches (token might have changed)
    - Token refresh occurs
    
    iOS Example:
    ```swift
    func application(_ application: UIApplication, 
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        // POST to /api/device-tokens/register with this token
    }
    ```
    """
    if not data.token or len(data.token) < 10:
        raise HTTPException(status_code=400, detail="Token inválido")
    
    try:
        await device_token_repo.create_or_update({
            "token": data.token,
            "platform": data.platform,
            "appVersion": data.app_version,
            "osVersion": data.os_version,
            "deviceModel": data.device_model
        })
        
        return RegisterTokenResponse(
            success=True,
            message="Token registrado correctamente"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registrando token: {str(e)}")


@router.delete("/unregister")
async def unregister_device_token(token: str):
    """
    Unregister a device token (disable notifications for this device).
    
    Call when user disables notifications or logs out.
    """
    if not token:
        raise HTTPException(status_code=400, detail="Token requerido")
    
    success = await device_token_repo.deactivate(token)
    
    if not success:
        raise HTTPException(status_code=404, detail="Token no encontrado")
    
    return {"success": True, "message": "Token desactivado"}


@router.delete("/cleanup-invalid")
async def cleanup_invalid_tokens():
    """
    Remove all invalid/expired device tokens from database.
    Call this to clean up tokens that fail with BadDeviceToken or DeviceTokenNotForTopic.
    """
    from clients import get_database
    
    db = get_database()
    
    # Get count before
    before_count = await db["device_tokens"].count_documents({})
    
    # Delete all tokens (nuclear option - users will re-register on next app open)
    result = await db["device_tokens"].delete_many({})
    
    return {
        "success": True,
        "message": "Tokens limpiados",
        "deleted": result.deleted_count,
        "before": before_count
    }
