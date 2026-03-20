"""QvaPay test endpoint for creating test invoices.

POST /api/v1/qvapay/test/create-invoice
  - Creates a test QvaPay invoice for testing payments
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from repositories.qvapay_repository import qvapay_invoices_repo
from repositories.payout_repository import payouts_repo
from services.payments.qvapay_service import QvaPayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qvapay/test", tags=["QvaPay - Testing"])

_service = QvaPayService(
    invoices_repo=qvapay_invoices_repo,
    payouts_repo=payouts_repo,
)


class CreateTestInvoiceRequest(BaseModel):
    order_id: str
    branch_id: str
    business_id: str
    amount: float = 10.00
    description: str = "Orden de prueba"
    products: Optional[list[dict]] = None


class CreateTestInvoiceResponse(BaseModel):
    success: bool
    payment_url: str
    transaction_uuid: str
    amount: float
    message: str


@router.post("/create-invoice", response_model=CreateTestInvoiceResponse)
async def create_test_invoice(request: CreateTestInvoiceRequest):
    """
    Crea una factura de prueba en QvaPay.
    
    Ejemplo de uso:
    ```json
    {
      "order_id": "67890abcdef12345",
      "branch_id": "branch_id_aqui",
      "business_id": "business_id_aqui",
      "amount": 25.00,
      "description": "Orden de prueba #123",
      "products": [
        {"name": "Producto 1", "price": 15.00, "quantity": 1},
        {"name": "Producto 2", "price": 10.00, "quantity": 1}
      ]
    }
    ```
    
    Respuesta incluye la URL de pago que puedes abrir en el navegador.
    """
    try:
        # Webhook URL
        webhook_url = None
        if settings.qvapay_base_url:
            webhook_url = f"{settings.qvapay_base_url}/api/v1/webhooks/qvapay"
        
        # Crear factura
        response = await _service.create_invoice(
            order_id=request.order_id,
            branch_id=request.branch_id,
            business_id=request.business_id,
            amount=request.amount,
            description=request.description,
            webhook_url=webhook_url,
            products=request.products,
        )
        
        logger.info(
            "Test invoice created order=%s uuid=%s url=%s",
            request.order_id,
            response.transaction_uuid,
            response.url,
        )
        
        return CreateTestInvoiceResponse(
            success=True,
            payment_url=response.url,
            transaction_uuid=response.transaction_uuid,
            amount=response.amount,
            message=f"Factura creada. Abre la URL para pagar: {response.url}",
        )
        
    except Exception as exc:
        logger.exception("Error creating test invoice: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear factura: {str(exc)}",
        ) from exc


@router.get("/info")
async def get_test_info():
    """
    Información sobre cómo probar QvaPay.
    """
    return {
        "message": "Endpoint de prueba para QvaPay",
        "steps": [
            "1. Crea una orden de prueba en tu sistema (o usa un ID existente)",
            "2. Llama a POST /api/v1/qvapay/test/create-invoice con los datos",
            "3. Abre la payment_url en tu navegador",
            "4. Paga con tu cuenta de QvaPay",
            "5. QvaPay enviará el webhook automáticamente",
            "6. Verifica en logs y base de datos que todo funcionó",
        ],
        "webhook_url": f"{settings.qvapay_base_url}/api/v1/webhooks/qvapay" if settings.qvapay_base_url else None,
        "success_url": f"{settings.qvapay_base_url}/api/v1/qvapay/success" if settings.qvapay_base_url else None,
        "cancel_url": f"{settings.qvapay_base_url}/api/v1/qvapay/cancel" if settings.qvapay_base_url else None,
        "auto_transfer_enabled": bool(settings.qvapay_platform_pin),
    }
