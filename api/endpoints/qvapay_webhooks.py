"""QvaPay webhook and callback endpoints.

POST /api/v1/webhooks/qvapay
  - Validates X-QvaPay-Signature header (HMAC-SHA256 of transaction_uuid).
  - Deduplicates by transactionUuid (idempotent).
  - On 'completed': marks order PAID and creates PendingPayout.
  - Always returns 200 so QvaPay stops retrying.

GET /api/v1/qvapay/success?transaction_uuid=xxx
  - User redirected here after successful payment.
  - Redirects to app deep link.

GET /api/v1/qvapay/cancel?transaction_uuid=xxx
  - User redirected here after canceling payment.
  - Marks invoice as cancelled and redirects to app deep link.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ValidationError

from core.config import settings
from repositories.qvapay_repository import qvapay_invoices_repo
from repositories.payout_repository import payouts_repo
from services.payments.qvapay_service import QvaPayService, QvaPayWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["QvaPay"])

_service = QvaPayService(
    invoices_repo=qvapay_invoices_repo,
    payouts_repo=payouts_repo,
)


class WebhookAck(BaseModel):
    received: bool = True


@router.post("/webhooks/qvapay", response_model=WebhookAck)
async def qvapay_webhook(
    request: Request,
    x_qvapay_signature: str = Header(default="", alias="X-QvaPay-Signature"),
):
    """
    Receive and process QvaPay payment notifications.

    Security:
      - Verifies signed=true in payload (CRITICAL)
      - HMAC-SHA256 signature verified against X-QvaPay-Signature header (if configured)
      - Returns 200 for all valid requests (including duplicates) so QvaPay
        does not retry excessively.
      
    Real QvaPay v2 webhook format:
      {
        "transaction_uuid": "string",
        "remote_id": "string",
        "status": "paid",
        "amount": "1.00",  // string, not number
        "signed": true,
        "created_at": "ISO8601",
        "updated_at": "ISO8601"
      }
    """
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
        # Security errors: unsigned webhook or invalid signature
        logger.warning("QvaPay webhook security error: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("QvaPay webhook processing error: %s", exc)
        # Return 500 so QvaPay retries later
        raise HTTPException(status_code=500, detail="Internal error") from exc

    return WebhookAck(received=True)


@router.get("/qvapay/success")
async def qvapay_success(
    transaction_uuid: str = Query(..., description="QvaPay transaction UUID"),
    remote_id: str = Query(None, description="Order ID (remote_id)"),
):
    """
    Success callback URL for QvaPay payments.
    User is redirected here after completing payment.
    Redirects to app deep link with transaction info.
    
    Query params from QvaPay:
      - transaction_uuid: UUID de la transacción
      - remote_id: ID de la orden (opcional)
    """
    try:
        result = await _service.handle_success_callback(transaction_uuid)
        
        # Build deep link with query parameters
        deeplink = settings.qvapay_success_deeplink
        params = [f"transaction_uuid={transaction_uuid}"]
        
        if result.get("found"):
            if result.get("order_id"):
                params.append(f"order_id={result['order_id']}")
            if result.get("status"):
                params.append(f"status={result['status']}")
        else:
            params.append("found=false")
        
        if remote_id:
            params.append(f"remote_id={remote_id}")
        
        # Add params to deep link
        redirect_url = f"{deeplink}?{'&'.join(params)}"
        
        logger.info(
            "QvaPay success redirect to deep link: %s (transaction=%s)",
            redirect_url,
            transaction_uuid,
        )
        
        # Redirect to deep link
        return RedirectResponse(url=redirect_url, status_code=303)
        
    except Exception as exc:
        logger.exception("Error handling QvaPay success callback: %s", exc)
        # On error, redirect to deep link with error flag
        error_deeplink = f"{settings.qvapay_success_deeplink}?error=true&transaction_uuid={transaction_uuid}"
        return RedirectResponse(url=error_deeplink, status_code=303)


@router.get("/qvapay/cancel")
async def qvapay_cancel(
    transaction_uuid: str = Query(..., description="QvaPay transaction UUID"),
    remote_id: str = Query(None, description="Order ID (remote_id)"),
):
    """
    Cancel callback URL for QvaPay payments.
    User is redirected here after canceling payment.
    Redirects to app deep link with cancellation info.
    
    Query params from QvaPay:
      - transaction_uuid: UUID de la transacción
      - remote_id: ID de la orden (opcional)
    """
    try:
        result = await _service.handle_cancel_callback(transaction_uuid)
        
        # Build deep link with query parameters
        deeplink = settings.qvapay_cancel_deeplink
        params = [f"transaction_uuid={transaction_uuid}"]
        
        if result.get("found"):
            params.append("found=true")
            if result.get("cancelled"):
                params.append("cancelled=true")
            if result.get("order_id"):
                params.append(f"order_id={result['order_id']}")
            if result.get("status"):
                params.append(f"status={result['status']}")
        else:
            params.append("found=false")
        
        if remote_id:
            params.append(f"remote_id={remote_id}")
        
        # Add params to deep link
        redirect_url = f"{deeplink}?{'&'.join(params)}"
        
        logger.info(
            "QvaPay cancel redirect to deep link: %s (transaction=%s)",
            redirect_url,
            transaction_uuid,
        )
        
        # Redirect to deep link
        return RedirectResponse(url=redirect_url, status_code=303)
        
    except Exception as exc:
        logger.exception("Error handling QvaPay cancel callback: %s", exc)
        # On error, redirect to deep link with error flag
        error_deeplink = f"{settings.qvapay_cancel_deeplink}?error=true&transaction_uuid={transaction_uuid}"
        return RedirectResponse(url=error_deeplink, status_code=303)
