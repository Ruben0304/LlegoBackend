"""Admin payout management endpoints.

GET  /admin/pending-payouts         — list payouts with payoutStatus=pending.
POST /admin/payouts/{id}/confirm    — mark a payout as confirmed (liquidated).
                                       For QvaPay payouts, attempts automatic transfer.

Authentication: static Bearer token via ADMIN_API_KEY env var.
"""

import logging
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from clients.mongodb_client import get_database
from core.config import settings
from domain.crypto_payments import PendingPayout
from repositories.payout_repository import payouts_repo
from services.payments.qvapay_transfer_service import qvapay_transfer_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin - Payouts"])

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> None:
    """Verify static admin API key."""
    key = settings.admin_api_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Admin API key not configured on server.",
        )
    if not credentials or not secrets.compare_digest(credentials.credentials, key):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PayoutOut(BaseModel):
    id: str
    orderId: str
    branchId: str
    businessId: str
    amount: float
    currency: str
    gateway: str
    externalTransactionId: str
    payoutStatus: str
    confirmedBy: Optional[str] = None
    confirmedAt: Optional[str] = None
    notes: Optional[str] = None
    createdAt: str
    updatedAt: str

    @classmethod
    def from_domain(cls, p: PendingPayout) -> "PayoutOut":
        return cls(
            id=str(p.id),
            orderId=str(p.orderId),
            branchId=str(p.branchId),
            businessId=str(p.businessId),
            amount=p.amount,
            currency=p.currency,
            gateway=p.gateway,
            externalTransactionId=p.externalTransactionId,
            payoutStatus=p.payoutStatus,
            confirmedBy=str(p.confirmedBy) if p.confirmedBy else None,
            confirmedAt=p.confirmedAt.isoformat() if p.confirmedAt else None,
            notes=p.notes,
            createdAt=p.createdAt.isoformat(),
            updatedAt=p.updatedAt.isoformat(),
        )


class PendingPayoutsResponse(BaseModel):
    total: int
    items: List[PayoutOut]


class ConfirmPayoutRequest(BaseModel):
    confirmed_by: str  # admin user ID (ObjectId string)
    notes: Optional[str] = None
    auto_transfer: bool = True  # Attempt automatic QvaPay transfer if applicable


class ConfirmPayoutResponse(BaseModel):
    payout: PayoutOut
    message: str = "Payout confirmed."
    transfer_transaction: Optional[str] = None  # QvaPay transaction UUID if auto-transferred


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/pending-payouts",
    response_model=PendingPayoutsResponse,
    dependencies=[Depends(_require_admin)],
)
async def list_pending_payouts(
    gateway: Optional[str] = Query(
        default=None,
        description="Filter by gateway: 'qvapay' or 'trondealer'",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List all completed payments pending manual liquidation."""
    items = await payouts_repo.get_pending(gateway=gateway, limit=limit, offset=offset)
    total = await payouts_repo.count_pending(gateway=gateway)
    return PendingPayoutsResponse(
        total=total,
        items=[PayoutOut.from_domain(p) for p in items],
    )


@router.post(
    "/payouts/{payout_id}/confirm",
    response_model=ConfirmPayoutResponse,
    dependencies=[Depends(_require_admin)],
)
async def confirm_payout(payout_id: str, body: ConfirmPayoutRequest):
    """
    Mark a payout as confirmed once the manual transfer has been executed.
    
    For QvaPay payouts with auto_transfer=True:
      - Fetches business qvapayUsername from branch
      - Attempts automatic transfer via QvaPay API
      - Stores transaction UUID in notes if successful
    
    Idempotent — returns 404 if already confirmed or not found.
    """
    # Get payout details before confirming
    payout_before = await payouts_repo.get_by_id(payout_id)
    if not payout_before:
        raise HTTPException(status_code=404, detail="Payout not found.")
    
    if payout_before.payoutStatus != "pending":
        raise HTTPException(status_code=400, detail="Payout already processed.")
    
    transfer_transaction: Optional[str] = None
    transfer_notes = body.notes or ""
    
    # Attempt automatic QvaPay transfer if enabled
    if (
        body.auto_transfer
        and payout_before.gateway == "qvapay"
        and settings.qvapay_platform_pin
    ):
        try:
            # Fetch branch to get qvapayUsername
            db = get_database()
            branch = await db.branches.find_one({"_id": payout_before.branchId})
            
            if not branch:
                logger.warning(
                    "Branch not found for payout id=%s branch_id=%s",
                    payout_id,
                    str(payout_before.branchId),
                )
            elif not branch.get("qvapayUsername"):
                logger.warning(
                    "Branch has no qvapayUsername configured id=%s",
                    str(payout_before.branchId),
                )
            else:
                qvapay_username = branch["qvapayUsername"]
                business_name = branch.get("name", "Negocio")
                
                # Attempt transfer
                logger.info(
                    "Attempting automatic QvaPay transfer payout=%s to=%s amount=%s",
                    payout_id,
                    qvapay_username,
                    payout_before.amount,
                )
                
                transfer_result = await qvapay_transfer_service.transfer_to_business(
                    amount=payout_before.amount,
                    qvapay_username=qvapay_username,
                    description=f"Pago por orden {str(payout_before.orderId)[:8]} - {business_name}",
                    pin=settings.qvapay_platform_pin,
                )
                
                transfer_transaction = transfer_result.transaction
                transfer_notes = (
                    f"Transferencia automática QvaPay: {transfer_transaction}\n"
                    f"Destinatario: {qvapay_username}\n"
                    f"{transfer_notes}"
                )
                
                logger.info(
                    "QvaPay auto-transfer successful payout=%s transaction=%s",
                    payout_id,
                    transfer_transaction,
                )
                
        except Exception as exc:
            # Log error but don't fail the confirmation
            # Admin can retry manually or transfer outside the system
            logger.error(
                "QvaPay auto-transfer failed payout=%s error=%s",
                payout_id,
                str(exc),
            )
            transfer_notes = (
                f"⚠️ Transferencia automática falló: {str(exc)}\n"
                f"Requiere transferencia manual.\n"
                f"{transfer_notes}"
            )
    
    # Confirm the payout
    payout = await payouts_repo.confirm(
        payout_id=payout_id,
        confirmed_by=body.confirmed_by,
        notes=transfer_notes.strip() or None,
    )
    
    if payout is None:
        raise HTTPException(
            status_code=404,
            detail="Payout not found or already confirmed.",
        )

    logger.info(
        "Payout confirmed id=%s gateway=%s amount=%s by=%s auto_transfer=%s",
        payout_id,
        payout.gateway,
        payout.amount,
        body.confirmed_by,
        transfer_transaction is not None,
    )
    
    return ConfirmPayoutResponse(
        payout=PayoutOut.from_domain(payout),
        message="Payout confirmed and transferred." if transfer_transaction else "Payout confirmed.",
        transfer_transaction=transfer_transaction,
    )
