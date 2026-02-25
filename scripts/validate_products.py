"""Script para validar que todos los productos tengan categoryId válido."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627/"
MONGODB_DATABASE = "llego"


async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]
    
    print("🔍 Validando productos...")
    
    # Obtener todos los IDs de categorías válidas
    categories = await db.product_categories.find({}).to_list(length=1000)
    valid_category_ids = {cat["_id"] for cat in categories}
    
    print(f"✅ Categorías válidas: {len(valid_category_ids)}")
    
    # Buscar productos con categoryId inválido
    all_products = await db.products.find({}).to_list(length=10000)
    
    invalid_products = []
    products_without_category = []
    
    for product in all_products:
        category_id = product.get("categoryId")
        
        if not category_id:
            products_without_category.append(product)
        elif category_id not in valid_category_ids:
            invalid_products.append(product)
    
    # Reporte
    print(f"\n📊 Resumen:")
    print(f"  • Total de productos: {len(all_products)}")
    print(f"  • Productos válidos: {len(all_products) - len(invalid_products) - len(products_without_category)}")
    print(f"  • Productos sin categoría: {len(products_without_category)}")
    print(f"  • Productos con categoría inválida: {len(invalid_products)}")
    
    if products_without_category:
        print(f"\n⚠️  Productos sin categoría:")
        for p in products_without_category[:10]:  # Mostrar solo los primeros 10
            print(f"  • {p['name']} (ID: {p['_id']}, Branch: {p.get('branchId', 'N/A')})")
        if len(products_without_category) > 10:
            print(f"  ... y {len(products_without_category) - 10} más")
    
    if invalid_products:
        print(f"\n❌ Productos con categoría inválida:")
        for p in invalid_products:
            print(f"  • {p['name']} (ID: {p['_id']})")
            print(f"    CategoryId inválido: {p.get('categoryId')}")
            print(f"    BranchId: {p.get('branchId')}")
    else:
        print(f"\n✅ Todos los productos tienen categorías válidas")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
