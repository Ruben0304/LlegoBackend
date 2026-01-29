"""
Script para ejecutar manualmente el worker de expiración de accesos.
Útil para limpiar accesos expirados acumulados.

IMPORTANTE: Este script requiere que MongoDB esté accesible.
Asegúrate de tener las variables de entorno configuradas.

Uso:
    python scripts/run_expiration_worker.py
"""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Verificar que las variables de entorno estén configuradas
required_env_vars = ['MONGODB_URL', 'DATABASE_NAME']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    print(f"❌ Error: Variables de entorno faltantes: {', '.join(missing_vars)}")
    print("\nAsegúrate de tener un archivo .env con:")
    print("  MONGODB_URL=mongodb://...")
    print("  DATABASE_NAME=nombre_db")
    sys.exit(1)


async def main():
    """Run the expiration worker once."""
    print("🔄 Ejecutando worker de expiración de accesos...")
    print("=" * 60)
    
    try:
        # Import here to avoid issues with dependencies
        from clients.mongodb_client import connect_to_mongo, close_mongo_connection
        from services.access_expiration_worker import expire_old_accesses
        
        # Connect to MongoDB
        print("📡 Conectando a MongoDB...")
        await connect_to_mongo()
        print("✅ Conectado a MongoDB")
        
        # Run the worker
        print("\n🔍 Buscando accesos expirados...")
        await expire_old_accesses()
        
        print("\n✅ Worker ejecutado exitosamente")
        print("=" * 60)
        print("\nAccesos expirados han sido marcados como inactivos.")
        print("Los usuarios afectados ya no tendrán acceso a los negocios/sucursales.")
        
        # Close connection
        await close_mongo_connection()
        
    except ImportError as e:
        print(f"\n❌ Error de importación: {e}")
        print("\nAsegúrate de:")
        print("  1. Activar el entorno virtual: .venv\\Scripts\\activate")
        print("  2. Instalar dependencias: pip install -r requirements.txt")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error al ejecutar el worker: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
