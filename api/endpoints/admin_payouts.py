"""Admin payout management endpoints.

GET  /admin/pending-payouts         — list payouts with payoutStatus=pending.
POST /admin/payouts/{id}/confirm    — mark a payout as confirmed (liquidated).

Authentication: static Bearer token via ADMIN_API_KEY env var.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core.config import settings
from domain.crypto_payments import PendingPayout
from repositories.payout_repository import payouts_repo

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
    if not credentials or credentials.credentials != key:
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


class ConfirmPayoutResponse(BaseModel):
    payout: PayoutOut
    message: str = "Payout confirmed."


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
    Idempotent — returns 404 if already confirmed or not found.
    """
    payout = await payouts_repo.confirm(
        payout_id=payout_id,
        confirmed_by=body.confirmed_by,
        notes=body.notes,
    )
    if payout is None:
        raise HTTPException(
            status_code=404,
            detail="Payout not found or already confirmed.",
        )

    logger.info(
        "Payout confirmed id=%s gateway=%s amount=%s by=%s",
        payout_id,
        payout.gateway,
        payout.amount,
        body.confirmed_by,
    )
    return ConfirmPayoutResponse(payout=PayoutOut.from_domain(payout))
