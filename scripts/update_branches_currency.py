"""
Script para actualizar todas las branches con acceptedCurrency='BOTH' y exchangeRate=500
"""
import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from clients.mongodb_client import connect_to_mongo, close_mongo_connection, get_database


async def update_branches_currency():
    """Actualiza todas las branches para aceptar ambas monedas con tasa de cambio de 500."""
    db = get_database()
    branches_collection = db["branches"]
    
    # Actualizar todas las branches
    result = await branches_collection.update_many(
        {},  # Sin filtro, actualiza todas
        {
            "$set": {
                "acceptedCurrency": "BOTH",
                "exchangeRate": 500
            }
        }
    )
    
    print(f"✅ Actualización completada:")
    print(f"   - Documentos encontrados: {result.matched_count}")
    print(f"   - Documentos actualizados: {result.modified_count}")
    
    # Verificar algunos ejemplos
    sample_branches = await branches_collection.find({}).limit(3).to_list(length=3)
    
    if sample_branches:
        print(f"\n📋 Ejemplos de branches actualizadas:")
        for branch in sample_branches:
            print(f"   - {branch.get('name', 'Sin nombre')}: "
                  f"acceptedCurrency={branch.get('acceptedCurrency')}, "
                  f"exchangeRate={branch.get('exchangeRate')}")


async def main():
    """Función principal."""
    print("🚀 Iniciando actualización de branches...")
    print("   Configurando: acceptedCurrency='BOTH', exchangeRate=500\n")
    
    try:
        # Conectar a MongoDB
        await connect_to_mongo()
        
        # Ejecutar actualización
        await update_branches_currency()
        
        print("\n✨ Script completado exitosamente!")
    except Exception as e:
        print(f"\n❌ Error durante la actualización: {e}")
        raise
    finally:
        # Cerrar conexión
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
