"""REST endpoint for registering bank transfers from iOS Shortcuts."""

import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from services.shortcut_transfer_service import shortcut_transfer_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shortcuts", tags=["shortcuts"])


def verify_api_key(x_api_key: Optional[str]) -> None:
    """Verify the static API key for Shortcuts authentication."""
    if not x_api_key or not settings.shortcuts_api_key:
        raise HTTPException(status_code=401, detail="API key requerida")
    if not secrets.compare_digest(x_api_key, settings.shortcuts_api_key):
        raise HTTPException(status_code=401, detail="API key inválida")


class RegisterTransferRequest(BaseModel):
    """Request model for registering a bank transfer."""

    transfer_id: str = Field(..., description="ID de la transferencia bancaria")
    amount: float = Field(..., gt=0, description="Monto de la transferencia")
    phone: Optional[str] = Field(
        default=None, description="Teléfono que recibió el SMS"
    )
    date: Optional[datetime] = Field(
        default=None, description="Fecha de la transferencia"
    )


class RegisterTransferResponse(BaseModel):
    """Response model for a registered transfer."""

    id: str
    transfer_id: str
    amount: float
    phone: Optional[str] = None
    date: Optional[datetime] = None
    activated: bool
    created_at: datetime


@router.post("/register-transfer", response_model=RegisterTransferResponse)
async def register_transfer(
    data: RegisterTransferRequest,
    x_api_key: Optional[str] = Header(None),
):
    """
    Register a bank transfer received via SMS.

    Called from iOS Shortcuts when a bank SMS is detected.
    Requires a static API key via X-API-Key header.
    """
    verify_api_key(x_api_key)

    try:
        transfer = await shortcut_transfer_service.register_transfer(
            transfer_id=data.transfer_id,
            amount=data.amount,
            phone=data.phone,
            date=data.date,
        )

        logger.info(
            f"Transfer registered: {transfer.transfer_id}, amount: {transfer.amount}"
        )

        return RegisterTransferResponse(
            id=transfer.id,
            transfer_id=transfer.transfer_id,
            amount=transfer.amount,
            phone=transfer.phone,
            date=transfer.date,
            activated=transfer.activated,
            created_at=transfer.created_at,
        )
    except Exception as e:
        logger.error(f"Error registering transfer: {e}")
        raise HTTPException(
            status_code=500, detail="Error al registrar la transferencia"
        ) from e
