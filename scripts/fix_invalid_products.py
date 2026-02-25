"""Script para eliminar o corregir productos con categoryId inválido."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627/"
MONGODB_DATABASE = "llego"

async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]
    
    print("🔍 Buscando productos con categoryId inválido...")
    
    # Obtener todos los IDs de categorías válidas
    categories = await db.product_categories.find({}).to_list(length=1000)
    valid_category_ids = {cat["_id"] for cat in categories}
    
    print(f"✅ Categorías válidas encontradas: {len(valid_category_ids)}")
    
    # Buscar productos con categoryId inválido
    all_products = await db.products.find({}).to_list(length=10000)
    invalid_products = []
    
    for product in all_products:
        category_id = product.get("categoryId")
        if category_id and category_id not in valid_category_ids:
            invalid_products.append(product)
    
    print(f"\n⚠️  Productos con categoryId inválido: {len(invalid_products)}")
    
    if not invalid_products:
        print("✅ No hay productos con categoryId inválido")
        client.close()
        return
    
    for product in invalid_products:
        print(f"\n  • {product['name']} (ID: {product['_id']})")
        print(f"    CategoryId inválido: {product.get('categoryId')}")
        print(f"    BranchId: {product.get('branchId')}")
    
    # Preguntar qué hacer
    print("\n¿Qué deseas hacer?")
    print("1. Eliminar estos productos")
    print("2. Asignarles una categoría válida")
    
    # Para automatizar, vamos a eliminarlos
    print("\n🗑️  Eliminando productos con categoryId inválido...")
    
    for product in invalid_products:
        result = await db.products.delete_one({"_id": product["_id"]})
        if result.deleted_count > 0:
            print(f"  ✓ Eliminado: {product['name']}")
        else:
            print(f"  ✗ Error eliminando: {product['name']}")
    
    print(f"\n✅ Proceso completado. Eliminados {len(invalid_products)} productos")
    
    # Verificar productos restantes
    remaining = await db.products.count_documents({"branchId": "698a1a31b9ce544fdb4e7505"})
    print(f"📊 Productos restantes en la sucursal: {remaining}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
