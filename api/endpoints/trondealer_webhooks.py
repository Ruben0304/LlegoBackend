"""TronDealer webhook endpoint.

POST /api/v1/webhooks/trondealer
  - Validates X-TronDealer-Signature (HMAC-SHA256 of raw body).
  - Optional IP whitelist (TRONDEALER_ALLOWED_IPS env var).
  - Deduplicates by wallet address (atomic PENDING → COMPLETED).
  - On deposit confirmed: marks order PAID and creates PendingPayout.
  - Always returns 200 on success so TronDealer stops retrying.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from repositories.trondealer_repository import trondealer_wallets_repo
from repositories.payout_repository import payouts_repo
from services.payments.trondealer_service import TronDealerService, TronDealerWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks - TronDealer"])

_service = TronDealerService(
    wallets_repo=trondealer_wallets_repo,
    payouts_repo=payouts_repo,
)


class WebhookAck(BaseModel):
    received: bool = True


@router.post("/trondealer", response_model=WebhookAck)
async def trondealer_webhook(
    request: Request,
    x_trondealer_signature: str = Header(default="", alias="X-TronDealer-Signature"),
):
    """
    Receive and process TronDealer deposit notifications.

    Security:
      - HMAC-SHA256 signature verified against X-TronDealer-Signature.
      - Optional IP whitelist via TRONDEALER_ALLOWED_IPS env var.
      - Returns 200 for valid requests (including duplicates).
    """
    raw_body = await request.body()

    # Extract client IP (behind proxy: use X-Forwarded-For first)
    client_ip: str = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )

    try:
        body_json = await request.json()
        payload = TronDealerWebhookPayload(**body_json)
    except (ValidationError, Exception) as exc:
        logger.warning("TronDealer webhook: malformed payload — %s", exc)
        return WebhookAck(received=True)

    try:
        await _service.handle_webhook(
            raw_body=raw_body,
            signature_header=x_trondealer_signature or None,
            client_ip=client_ip or None,
            payload=payload,
        )
    except ValueError as exc:
        logger.warning("TronDealer webhook security error: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("TronDealer webhook processing error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error") from exc

    return WebhookAck(received=True)
