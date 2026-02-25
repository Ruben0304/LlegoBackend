"""Script para convertir categoryId de ObjectId a string en todos los productos."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

MONGODB_URL = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627/"
MONGODB_DATABASE = "llego"


async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]
    
    print("🔍 Buscando productos con categoryId como ObjectId...")
    
    # Obtener todos los productos
    all_products = await db.products.find({}).to_list(length=10000)
    
    products_to_fix = []
    for product in all_products:
        category_id = product.get("categoryId")
        if category_id and isinstance(category_id, ObjectId):
            products_to_fix.append(product)
    
    print(f"✅ Productos encontrados: {len(all_products)}")
    print(f"⚠️  Productos con categoryId como ObjectId: {len(products_to_fix)}")
    
    if not products_to_fix:
        print("\n✅ No hay productos que arreglar")
        client.close()
        return
    
    print(f"\n🔧 Convirtiendo categoryId de ObjectId a string...")
    
    fixed_count = 0
    for product in products_to_fix:
        try:
            # Convertir ObjectId a string
            new_category_id = str(product["categoryId"])
            
            result = await db.products.update_one(
                {"_id": product["_id"]},
                {"$set": {"categoryId": new_category_id}}
            )
            
            if result.modified_count > 0:
                fixed_count += 1
                print(f"  ✓ {product['name']}: {product['categoryId']} → {new_category_id}")
        
        except Exception as e:
            print(f"  ✗ Error con {product['name']}: {e}")
    
    print(f"\n✅ Proceso completado: {fixed_count}/{len(products_to_fix)} productos actualizados")
    
    # Verificar
    print(f"\n🔍 Verificando...")
    remaining = await db.products.count_documents({"categoryId": {"$type": "objectId"}})
    print(f"   Productos con categoryId como ObjectId: {remaining}")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
