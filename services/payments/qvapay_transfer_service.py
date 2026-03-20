"""QvaPay transfer service for automatic payouts to businesses.

Handles automatic balance transfers from platform account to business QvaPay accounts
when a payout is confirmed.
"""

import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

QVAPAY_API_BASE = "https://api.qvapay.com"


# ---------------------------------------------------------------------------
# Pydantic schemas for QvaPay Transfer API
# ---------------------------------------------------------------------------


class QvaPayTransferRequest(BaseModel):
    amount: float
    to: str  # UUID, email, username or phone
    pin: str
    description: Optional[str] = None


class QvaPayTransferResponse(BaseModel):
    success: bool
    message: str
    transaction: str  # UUID of the transaction


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class QvaPayTransferService:
    """Service for transferring balance to business QvaPay accounts."""

    async def transfer_to_business(
        self,
        amount: float,
        qvapay_username: str,
        description: str,
        pin: str,
    ) -> QvaPayTransferResponse:
        """
        Transfer balance from platform account to a business QvaPay account.
        
        Args:
            amount: Amount to transfer (must be > 0)
            qvapay_username: Business QvaPay username, email, UUID or phone
            description: Transfer description/note
            pin: Platform account PIN (4 or 6 digits)
            
        Returns:
            QvaPayTransferResponse with transaction UUID
            
        Raises:
            RuntimeError: If credentials not configured or transfer fails
        """
        if not settings.qvapay_app_id or not settings.qvapay_app_secret:
            raise RuntimeError("QvaPay credentials not configured.")

        payload = {
            "amount": amount,
            "to": qvapay_username,
            "pin": pin,
            "description": description,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{QVAPAY_API_BASE}/transaction/transfer",
                json=payload,
                headers={
                    "app-id": settings.qvapay_app_id,
                    "app-secret": settings.qvapay_app_secret,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(
                "QvaPay transfer failed to=%s amount=%s status=%s body=%s",
                qvapay_username,
                amount,
                response.status_code,
                error_detail,
            )
            
            # Parse common errors
            if response.status_code == 400:
                if "PIN" in error_detail or "pin" in error_detail:
                    raise RuntimeError("PIN incorrecto")
                elif "balance" in error_detail.lower():
                    raise RuntimeError("Balance insuficiente en cuenta de plataforma")
                elif "propia cuenta" in error_detail.lower():
                    raise RuntimeError("No se puede transferir a la propia cuenta")
            elif response.status_code == 404:
                raise RuntimeError(f"Usuario QvaPay no encontrado: {qvapay_username}")
            elif response.status_code == 429:
                raise RuntimeError("Demasiadas solicitudes, intenta en 10 segundos")
            
            raise RuntimeError(f"Error en transferencia QvaPay: {response.status_code} {error_detail}")

        data = response.json()
        transfer_resp = QvaPayTransferResponse(**data)

        logger.info(
            "QvaPay transfer completed to=%s amount=%s transaction=%s",
            qvapay_username,
            amount,
            transfer_resp.transaction,
        )
        
        return transfer_resp


qvapay_transfer_service = QvaPayTransferService()
