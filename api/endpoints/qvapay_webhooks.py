"""QvaPay webhook endpoint.

POST /api/v1/webhooks/qvapay
  - Validates X-QvaPay-Signature header (HMAC-SHA256 of transaction_uuid).
  - Deduplicates by transactionUuid (idempotent).
  - On 'completed': marks order PAID and creates PendingPayout.
  - Always returns 200 so QvaPay stops retrying.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError

from repositories.qvapay_repository import qvapay_invoices_repo
from repositories.payout_repository import payouts_repo
from services.payments.qvapay_service import QvaPayService, QvaPayWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks - QvaPay"])

_service = QvaPayService(
    invoices_repo=qvapay_invoices_repo,
    payouts_repo=payouts_repo,
)


class WebhookAck(BaseModel):
    received: bool = True


@router.post("/qvapay", response_model=WebhookAck)
async def qvapay_webhook(
    request: Request,
    x_qvapay_signature: str = Header(default="", alias="X-QvaPay-Signature"),
):
    """
    Receive and process QvaPay payment notifications.

    Security:
      - HMAC-SHA256 signature verified against X-QvaPay-Signature header.
      - Returns 200 for all valid requests (including duplicates) so QvaPay
        does not retry excessively.
    """
    raw_body = await request.body()

    try:
        body_json = await request.json()
        payload = QvaPayWebhookPayload(**body_json)
    except (ValidationError, Exception) as exc:
        logger.warning("QvaPay webhook: malformed payload — %s", exc)
        # Return 200 to prevent infinite retries on bad payloads
        return WebhookAck(received=True)

    try:
        await _service.handle_webhook(
            payload=payload,
            signature_header=x_qvapay_signature or None,
        )
    except ValueError as exc:
        logger.warning("QvaPay webhook security error: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("QvaPay webhook processing error: %s", exc)
        # Return 500 so QvaPay retries later
        raise HTTPException(status_code=500, detail="Internal error") from exc

    return WebhookAck(received=True)
