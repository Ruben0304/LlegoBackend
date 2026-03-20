"""QvaPay webhook and callback endpoints.

POST /api/v1/webhooks/qvapay
  - Validates X-QvaPay-Signature header (HMAC-SHA256 of transaction_uuid).
  - Deduplicates by transactionUuid (idempotent).
  - On 'completed': marks order PAID and creates PendingPayout.
  - Always returns 200 so QvaPay stops retrying.

GET /api/v1/qvapay/success?transaction_uuid=xxx
  - User redirected here after successful payment.
  - Returns HTML page with success message.

GET /api/v1/qvapay/cancel?transaction_uuid=xxx
  - User redirected here after canceling payment.
  - Marks invoice as cancelled and returns HTML page.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

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


@router.get("/qvapay/success", response_class=HTMLResponse)
async def qvapay_success(
    transaction_uuid: str = Query(..., description="QvaPay transaction UUID"),
    remote_id: str = Query(None, description="Order ID (remote_id)"),
):
    """
    Success callback URL for QvaPay payments.
    User is redirected here after completing payment.
    
    Query params from QvaPay:
      - transaction_uuid: UUID de la transacción
      - remote_id: ID de la orden (opcional)
    """
    try:
        result = await _service.handle_success_callback(transaction_uuid)
        
        if result["found"]:
            html_content = f"""
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Pago Exitoso</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 3rem;
                        border-radius: 20px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }}
                    .success-icon {{
                        width: 80px;
                        height: 80px;
                        background: #10b981;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin: 0 auto 1.5rem;
                    }}
                    .success-icon::after {{
                        content: "✓";
                        color: white;
                        font-size: 48px;
                        font-weight: bold;
                    }}
                    h1 {{
                        color: #1f2937;
                        margin-bottom: 1rem;
                        font-size: 2rem;
                    }}
                    p {{
                        color: #6b7280;
                        line-height: 1.6;
                        margin-bottom: 0.5rem;
                    }}
                    .order-id {{
                        background: #f3f4f6;
                        padding: 1rem;
                        border-radius: 10px;
                        margin: 1.5rem 0;
                        font-family: monospace;
                        color: #374151;
                    }}
                    .close-btn {{
                        background: #667eea;
                        color: white;
                        border: none;
                        padding: 1rem 2rem;
                        border-radius: 10px;
                        font-size: 1rem;
                        cursor: pointer;
                        margin-top: 1rem;
                        transition: background 0.3s;
                    }}
                    .close-btn:hover {{
                        background: #5568d3;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon"></div>
                    <h1>¡Pago Exitoso!</h1>
                    <p>Tu pago ha sido procesado correctamente.</p>
                    <p>Recibirás una notificación cuando tu pedido sea confirmado.</p>
                    <div class="order-id">
                        <strong>ID de Transacción:</strong><br>
                        {transaction_uuid[:8]}...
                        {f'<br><br><strong>Orden:</strong><br>{remote_id}' if remote_id else ''}
                    </div>
                    <button class="close-btn" onclick="window.close()">Cerrar</button>
                </div>
            </body>
            </html>
            """
        else:
            html_content = """
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Transacción No Encontrada</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 3rem;
                        border-radius: 20px;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        text-align: center;
                        max-width: 500px;
                    }
                    .warning-icon {
                        width: 80px;
                        height: 80px;
                        background: #f59e0b;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin: 0 auto 1.5rem;
                        font-size: 48px;
                    }
                    h1 {
                        color: #1f2937;
                        margin-bottom: 1rem;
                    }
                    p {
                        color: #6b7280;
                        line-height: 1.6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="warning-icon">⚠️</div>
                    <h1>Transacción No Encontrada</h1>
                    <p>No pudimos encontrar información sobre esta transacción.</p>
                    <p>Por favor, contacta con soporte si crees que esto es un error.</p>
                </div>
            </body>
            </html>
            """
        
        return HTMLResponse(content=html_content)
        
    except Exception as exc:
        logger.exception("Error handling QvaPay success callback: %s", exc)
        raise HTTPException(status_code=500, detail="Error processing callback") from exc


@router.get("/qvapay/cancel", response_class=HTMLResponse)
async def qvapay_cancel(
    transaction_uuid: str = Query(..., description="QvaPay transaction UUID"),
    remote_id: str = Query(None, description="Order ID (remote_id)"),
):
    """
    Cancel callback URL for QvaPay payments.
    User is redirected here after canceling payment.
    
    Query params from QvaPay:
      - transaction_uuid: UUID de la transacción
      - remote_id: ID de la orden (opcional)
    """
    try:
        result = await _service.handle_cancel_callback(transaction_uuid)
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Pago Cancelado</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                .cancel-icon {{
                    width: 80px;
                    height: 80px;
                    background: #ef4444;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 1.5rem;
                }}
                .cancel-icon::after {{
                    content: "✕";
                    color: white;
                    font-size: 48px;
                    font-weight: bold;
                }}
                h1 {{
                    color: #1f2937;
                    margin-bottom: 1rem;
                    font-size: 2rem;
                }}
                p {{
                    color: #6b7280;
                    line-height: 1.6;
                    margin-bottom: 0.5rem;
                }}
                .info-box {{
                    background: #fef3c7;
                    padding: 1rem;
                    border-radius: 10px;
                    margin: 1.5rem 0;
                    color: #92400e;
                    border-left: 4px solid #f59e0b;
                }}
                .close-btn {{
                    background: #6b7280;
                    color: white;
                    border: none;
                    padding: 1rem 2rem;
                    border-radius: 10px;
                    font-size: 1rem;
                    cursor: pointer;
                    margin-top: 1rem;
                    transition: background 0.3s;
                }}
                .close-btn:hover {{
                    background: #4b5563;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="cancel-icon"></div>
                <h1>Pago Cancelado</h1>
                <p>Has cancelado el proceso de pago.</p>
                <div class="info-box">
                    <strong>ℹ️ Información:</strong><br>
                    {"Tu pedido ha sido cancelado." if result["cancelled"] else "No se realizó ningún cargo a tu cuenta."}
                </div>
                <p>Puedes intentar realizar el pago nuevamente cuando lo desees.</p>
                <button class="close-btn" onclick="window.close()">Cerrar</button>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as exc:
        logger.exception("Error handling QvaPay cancel callback: %s", exc)
        raise HTTPException(status_code=500, detail="Error processing callback") from exc
