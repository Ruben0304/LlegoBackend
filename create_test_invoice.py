"""Script para crear una factura de prueba en QvaPay.

Uso:
    python create_test_invoice.py
"""

import asyncio
import httpx
from datetime import datetime

# Configuración QvaPay
QVAPAY_APP_ID = "1c62423d-c474-4b08-b032-83072d58913a"
QVAPAY_APP_SECRET = "2556ed83ea6e04531e2d5f9486dec005ce9ac82269ce3fe990"
QVAPAY_API_BASE = "https://api.qvapay.com/v2"

# URLs de tu backend en producción
BACKEND_URL = "https://llegobackend-production.up.railway.app"
WEBHOOK_URL = f"{BACKEND_URL}/api/v1/webhooks/qvapay"
SUCCESS_URL = f"{BACKEND_URL}/api/v1/qvapay/success"
CANCEL_URL = f"{BACKEND_URL}/api/v1/qvapay/cancel"


async def create_invoice():
    """Crea una factura de prueba en QvaPay."""
    
    # Datos de la factura
    payload = {
        "amount": 1.00,
        "description": "Orden de prueba - Testing webhook",
        "remote_id": f"test-order-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "webhook": WEBHOOK_URL,
        "success_url": SUCCESS_URL,
        "cancel_url": CANCEL_URL,
        "products": [
            {
                "name": "Producto de prueba",
                "price": 1.00,
                "quantity": 1
            }
        ]
    }
    
    print("=" * 70)
    print("🚀 CREANDO FACTURA DE PRUEBA EN QVAPAY")
    print("=" * 70)
    print()
    print(f"💰 Monto: ${payload['amount']}")
    print(f"📝 Descripción: {payload['description']}")
    print(f"🆔 Remote ID: {payload['remote_id']}")
    print(f"🔔 Webhook: {WEBHOOK_URL}")
    print(f"✅ Success URL: {SUCCESS_URL}")
    print(f"❌ Cancel URL: {CANCEL_URL}")
    print()
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                f"{QVAPAY_API_BASE}/create_invoice",
                json=payload,
                headers={
                    "app-id": QVAPAY_APP_ID,
                    "app-secret": QVAPAY_APP_SECRET,
                    "Content-Type": "application/json",
                },
            )
            
            if response.status_code != 200:
                print(f"❌ Error: {response.status_code}")
                print(f"📄 Response: {response.text}")
                return
            
            data = response.json()
            
            print("=" * 70)
            print("✅ FACTURA CREADA EXITOSAMENTE")
            print("=" * 70)
            print()
            print(f"🔗 URL de pago: {data['url']}")
            print(f"🆔 Transaction UUID: {data['transaction_uuid']}")
            print(f"💰 Monto: ${data['amount']}")
            print(f"🆔 Remote ID: {payload['remote_id']}")
            print()
            print("=" * 70)
            print("📋 INSTRUCCIONES:")
            print("=" * 70)
            print()
            print("1. Abre la URL de pago en tu navegador:")
            print(f"   {data['url']}")
            print()
            print("2. Completa el pago con tu cuenta QvaPay")
            print()
            print("3. QvaPay enviará automáticamente:")
            print("   - POST webhook a tu backend")
            print("   - Redirect a success URL")
            print()
            print("4. Tu backend automáticamente:")
            print("   ✅ Validará signed=true")
            print("   ✅ Verificará status='paid'")
            print("   ✅ Marcará la orden como pagada")
            print("   ✅ Creará PendingPayout")
            print("   ✅ Transferirá saldo al negocio (si tiene qvapayUsername)")
            print()
            print("5. Para verificar en MongoDB:")
            print()
            print(f'   db.qvapay_invoices.findOne({{transactionUuid: "{data["transaction_uuid"]}"}})') 
            print(f'   // Debe tener status: "completed"')
            print()
            print(f'   db.orders.findOne({{_id: ObjectId("{payload["remote_id"]}")}})') 
            print(f'   // Debe tener paymentStatus: "completed", status: "pending_acceptance"')
            print()
            print(f'   db.pending_payouts.findOne({{externalTransactionId: "{data["transaction_uuid"]}"}})') 
            print(f'   // Debe existir con gateway: "qvapay"')
            print(f'   // Si tienes PIN: payoutStatus: "confirmed"')
            print(f'   // Si NO tienes PIN: payoutStatus: "pending"')
            print()
            print("6. Para ver logs del backend:")
            print("   railway logs --tail")
            print()
            print("=" * 70)
            
        except Exception as e:
            print(f"❌ Error al crear factura: {e}")


if __name__ == "__main__":
    asyncio.run(create_invoice())
