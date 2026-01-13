"""REST endpoints for push notifications."""
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from services.push_notification_service import push_service
from repositories.device_token_repository import device_token_repo

router = APIRouter(prefix="/api/push", tags=["Push Notifications"])


class SendPushRequest(BaseModel):
    """Request to send a push notification."""
    title: str
    body: str
    scheduled_at: Optional[datetime] = None  # ISO 8601 format, if None sends immediately
    data: Optional[dict] = None  # Extra data payload


class SendPushResponse(BaseModel):
    """Response after sending push notification."""
    success: bool
    message: str
    bundle_id: str
    total_tokens: int
    sent: int
    failed: int
    scheduled: bool
    scheduled_at: Optional[datetime] = None


async def _send_push_delayed(
    tokens: list,
    title: str,
    body: str,
    bundle_id: str,
    data: Optional[dict],
    delay_seconds: float
):
    """Background task to send push after delay."""
    await asyncio.sleep(delay_seconds)
    await push_service.send_to_all(
        tokens=tokens,
        title=title,
        body=body,
        data=data,
        platform="IOS",
        bundle_id=bundle_id
    )


@router.post("/clientes", response_model=SendPushResponse)
async def send_push_clientes(
    request: SendPushRequest,
    background_tasks: BackgroundTasks
):
    """
    Send push notification to all Llego Clientes users.
    Bundle ID: com.ruben.LlegoiOS
    
    If scheduled_at is provided, the notification will be sent at that time.
    Otherwise, it sends immediately.
    """
    bundle_id = "com.ruben.LlegoiOS"
    
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    if not ios_tokens:
        raise HTTPException(status_code=404, detail="No hay dispositivos iOS registrados")
    
    # Check if scheduled
    if request.scheduled_at:
        now = datetime.utcnow()
        if request.scheduled_at <= now:
            raise HTTPException(status_code=400, detail="La fecha programada debe ser en el futuro")
        
        delay = (request.scheduled_at - now).total_seconds()
        background_tasks.add_task(
            _send_push_delayed,
            ios_tokens,
            request.title,
            request.body,
            bundle_id,
            request.data,
            delay
        )
        
        return SendPushResponse(
            success=True,
            message=f"Notificación programada para {request.scheduled_at.isoformat()}",
            bundle_id=bundle_id,
            total_tokens=len(ios_tokens),
            sent=0,
            failed=0,
            scheduled=True,
            scheduled_at=request.scheduled_at
        )
    
    # Send immediately
    result = await push_service.send_to_all(
        tokens=ios_tokens,
        title=request.title,
        body=request.body,
        data=request.data,
        platform="IOS",
        bundle_id=bundle_id
    )
    
    return SendPushResponse(
        success=result["success"] > 0,
        message=f"Enviado a {result['success']} dispositivos",
        bundle_id=bundle_id,
        total_tokens=len(ios_tokens),
        sent=result["success"],
        failed=result["failed"],
        scheduled=False
    )


@router.post("/negocios", response_model=SendPushResponse)
async def send_push_negocios(
    request: SendPushRequest,
    background_tasks: BackgroundTasks
):
    """
    Send push notification to all Llego Negocios users.
    Bundle ID: com.llego.business.LlegoBusiness
    
    If scheduled_at is provided, the notification will be sent at that time.
    Otherwise, it sends immediately.
    """
    bundle_id = "com.llego.business.LlegoBusiness"
    
    tokens = await device_token_repo.get_all_active()
    ios_tokens = [t.token for t in tokens if t.platform == "IOS"]
    
    if not ios_tokens:
        raise HTTPException(status_code=404, detail="No hay dispositivos iOS registrados")
    
    # Check if scheduled
    if request.scheduled_at:
        now = datetime.utcnow()
        if request.scheduled_at <= now:
            raise HTTPException(status_code=400, detail="La fecha programada debe ser en el futuro")
        
        delay = (request.scheduled_at - now).total_seconds()
        background_tasks.add_task(
            _send_push_delayed,
            ios_tokens,
            request.title,
            request.body,
            bundle_id,
            request.data,
            delay
        )
        
        return SendPushResponse(
            success=True,
            message=f"Notificación programada para {request.scheduled_at.isoformat()}",
            bundle_id=bundle_id,
            total_tokens=len(ios_tokens),
            sent=0,
            failed=0,
            scheduled=True,
            scheduled_at=request.scheduled_at
        )
    
    # Send immediately
    result = await push_service.send_to_all(
        tokens=ios_tokens,
        title=request.title,
        body=request.body,
        data=request.data,
        platform="IOS",
        bundle_id=bundle_id
    )
    
    return SendPushResponse(
        success=result["success"] > 0,
        message=f"Enviado a {result['success']} dispositivos",
        bundle_id=bundle_id,
        total_tokens=len(ios_tokens),
        sent=result["success"],
        failed=result["failed"],
        scheduled=False
    )
