"""
Script para probar el endpoint de Stripe Payment Link.

Uso:
    python scripts/test_recharge_link.py

Requisitos:
    - Servidor corriendo en localhost:8000
    - Usuario registrado con JWT válido
    - Variables de entorno de Stripe configuradas
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración
BASE_URL = "http://localhost:8000"
JWT_TOKEN = os.getenv("TEST_JWT_TOKEN", "")  # Agregar tu JWT de prueba aquí


async def test_create_recharge_link():
    """Probar la creación de un Payment Link."""
    print("🧪 Probando creación de Payment Link...")
    print("-" * 50)
    
    if not JWT_TOKEN:
        print("❌ Error: JWT_TOKEN no configurado")
        print("   Agrega TEST_JWT_TOKEN a tu archivo .env")
        return
    
    async with httpx.AsyncClient() as client:
        try:
            # Crear Payment Link
            response = await client.post(
                f"{BASE_URL}/stripe/create-recharge-link",
                headers={
                    "Authorization": f"Bearer {JWT_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "currency": "usd",
                    "description": "Recarga internacional para Llego Wallet"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Payment Link creado exitosamente!")
                print(f"\n📋 Detalles:")
                print(f"   Link ID: {data['link_id']}")
                print(f"   User ID: {data['user_id']}")
                print(f"   Expira: {data['expires_at'] or 'Nunca'}")
                print(f"\n🔗 URL del Payment Link:")
                print(f"   {data['payment_link']}")
                print(f"\n💡 Comparte este link con alguien para que te envíe dinero")
                print(f"   Pueden pagar con tarjeta internacional")
                print(f"   Monto mínimo: $5 USD")
                print(f"   Monto máximo: $1000 USD")
                
            elif response.status_code == 401:
                print("❌ Error de autenticación")
                print(f"   {response.json()['detail']}")
                print("\n💡 Asegúrate de que tu JWT_TOKEN sea válido")
                
            elif response.status_code == 404:
                print("❌ Usuario no encontrado")
                print(f"   {response.json()['detail']}")
                
            else:
                print(f"❌ Error {response.status_code}")
                print(f"   {response.json()}")
                
        except httpx.ConnectError:
            print("❌ Error de conexión")
            print("   Asegúrate de que el servidor esté corriendo en localhost:8000")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")


async def test_get_stripe_config():
    """Probar el endpoint de configuración de Stripe."""
    print("\n🧪 Probando obtención de configuración de Stripe...")
    print("-" * 50)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/stripe/config")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Configuración obtenida exitosamente!")
                print(f"\n📋 Publishable Key:")
                print(f"   {data['publishable_key'][:20]}...")
                
            else:
                print(f"❌ Error {response.status_code}")
                print(f"   {response.json()}")
                
        except httpx.ConnectError:
            print("❌ Error de conexión")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")


async def main():
    """Ejecutar todas las pruebas."""
    print("\n" + "=" * 50)
    print("🚀 Test de Stripe Payment Link")
    print("=" * 50 + "\n")
    
    # Verificar variables de entorno
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        print("⚠️  Advertencia: STRIPE_SECRET_KEY no configurada")
        print("   Agrega las variables de Stripe a tu archivo .env\n")
    
    # Ejecutar pruebas
    await test_get_stripe_config()
    await test_create_recharge_link()
    
    print("\n" + "=" * 50)
    print("✨ Pruebas completadas")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
