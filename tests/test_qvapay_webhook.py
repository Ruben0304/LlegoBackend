"""Script para probar el webhook de QvaPay localmente.

Simula una notificación de pago completado desde QvaPay.

Uso:
    python tests/test_qvapay_webhook.py
"""

import asyncio
import hashlib
import hmac
import httpx
from datetime import datetime

# Configuración
BACKEND_URL = "http://localhost:8000"  # Cambia si usas otro puerto
# BACKEND_URL = "https://llegobackend-production.up.railway.app"  # Para producción

# Datos de prueba - reemplaza con datos reales de tu sistema
TEST_TRANSACTION_UUID = "test-7c9e6679-7425-40de-944b-e07fc1f90ae7"
TEST_REMOTE_ID = "67890abcdef12345"  # ID de una orden real en tu DB
TEST_AMOUNT = 25.00

# Webhook secret (debe coincidir con QVAPAY_WEBHOOK_SECRET en .env)
# Si está vacío en .env, la verificación se salta
WEBHOOK_SECRET = ""  # Déjalo vacío si no lo has configurado


def generate_signature(transaction_uuid: str, secret: str) -> str:
    """Genera la firma HMAC-SHA256 como lo hace QvaPay."""
    if not secret:
        return ""
    return hmac.new(
        secret.encode(),
        transaction_uuid.encode(),
        hashlib.sha256,
    ).hexdigest()


async def test_webhook():
    """Envía un webhook de prueba al backend."""
    
    # Payload del webhook (simula lo que envía QvaPay)
    payload = {
        "transaction_uuid": TEST_TRANSACTION_UUID,
        "remote_id": TEST_REMOTE_ID,
        "amount": TEST_AMOUNT,
        "status": "completed",  # Cambia a "pending" o "failed" para probar otros casos
        "description": "Pago de prueba",
        "app_id": "1c62423d-c474-4b08-b032-83072d58913a",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    
    # Genera la firma
    signature = generate_signature(TEST_TRANSACTION_UUID, WEBHOOK_SECRET)
    
    headers = {
        "Content-Type": "application/json",
    }
    if signature:
        headers["X-QvaPay-Signature"] = signature
    
    print(f"🚀 Enviando webhook de prueba a {BACKEND_URL}/api/v1/webhooks/qvapay")
    print(f"📦 Payload: {payload}")
    print(f"🔐 Signature: {signature or '(sin firma)'}")
    print()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/webhooks/qvapay",
                json=payload,
                headers=headers,
            )
            
            print(f"✅ Status: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
            if response.status_code == 200:
                print("\n✨ Webhook procesado exitosamente!")
                print("\n📋 Verifica en tu base de datos:")
                print(f"   - Invoice con transactionUuid: {TEST_TRANSACTION_UUID}")
                print(f"   - Orden {TEST_REMOTE_ID} debe estar en estado 'pending_acceptance'")
                print(f"   - PendingPayout creado para la orden")
                if WEBHOOK_SECRET:
                    print(f"   - Si tienes QVAPAY_PLATFORM_PIN configurado, debe haber una transferencia automática")
            else:
                print(f"\n❌ Error: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error al enviar webhook: {e}")


async def test_success_callback():
    """Prueba el callback de éxito."""
    print("\n" + "="*60)
    print("🧪 Probando callback de éxito...")
    print("="*60 + "\n")
    
    url = f"{BACKEND_URL}/api/v1/qvapay/success?transaction_uuid={TEST_TRANSACTION_UUID}"
    print(f"🌐 Abriendo: {url}")
    print("   (Deberías ver una página HTML de éxito)")


async def test_cancel_callback():
    """Prueba el callback de cancelación."""
    print("\n" + "="*60)
    print("🧪 Probando callback de cancelación...")
    print("="*60 + "\n")
    
    url = f"{BACKEND_URL}/api/v1/qvapay/cancel?transaction_uuid={TEST_TRANSACTION_UUID}"
    print(f"🌐 Abriendo: {url}")
    print("   (Deberías ver una página HTML de cancelación)")


async def main():
    """Ejecuta todas las pruebas."""
    print("\n" + "="*60)
    print("🧪 PRUEBA DE WEBHOOK QVAPAY")
    print("="*60 + "\n")
    
    print("⚠️  IMPORTANTE:")
    print("   1. Asegúrate de que tu backend esté corriendo")
    print("   2. Crea una orden de prueba en tu DB y usa su ID en TEST_REMOTE_ID")
    print("   3. Si tienes QVAPAY_WEBHOOK_SECRET configurado, actualiza WEBHOOK_SECRET aquí")
    print()
    
    input("Presiona ENTER para continuar...")
    
    # Prueba el webhook
    await test_webhook()
    
    # Prueba los callbacks (opcional)
    print("\n¿Quieres probar los callbacks de éxito/cancelación? (s/n): ", end="")
    if input().lower() == 's':
        await test_success_callback()
        await test_cancel_callback()


if __name__ == "__main__":
    asyncio.run(main())
