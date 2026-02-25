"""Script para agregar 40 productos de muestra a una sucursal específica."""

import asyncio
from datetime import datetime
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient


# Configuración directa
MONGODB_URL = "mongodb://mongo:TghyWYcXkIRgeYQWTeZcTeFGJNaMbDLi@shinkansen.proxy.rlwy.net:27627/"
MONGODB_DATABASE = "llego"
BRANCH_ID = "698a1a31b9ce544fdb4e7505"


# Productos de muestra por categoría (restaurante) - 40 productos
SAMPLE_PRODUCTS = [
    # Desayuno (5 productos)
    {
        "name": "Tostadas Francesas",
        "description": "Tostadas con miel, frutas frescas y mantequilla",
        "weight": "250g",
        "price": 5.50,
        "category": "Desayuno"
    },
    {
        "name": "Omelette de Queso",
        "description": "Omelette con queso cheddar y vegetales",
        "weight": "200g",
        "price": 6.00,
        "category": "Desayuno"
    },
    {
        "name": "Pancakes con Maple",
        "description": "Stack de pancakes con jarabe de maple y mantequilla",
        "weight": "300g",
        "price": 6.50,
        "category": "Desayuno"
    },
    {
        "name": "Huevos Benedictinos",
        "description": "Huevos pochados con jamón y salsa holandesa",
        "weight": "280g",
        "price": 8.00,
        "category": "Desayuno"
    },
    {
        "name": "Croissant Relleno",
        "description": "Croissant con jamón, queso y huevo",
        "weight": "180g",
        "price": 5.00,
        "category": "Desayuno"
    },
    # Entrantes (5 productos)
    {
        "name": "Ensalada César",
        "description": "Lechuga romana, crutones, parmesano y aderezo césar",
        "weight": "300g",
        "price": 7.50,
        "category": "Entrantes"
    },
    {
        "name": "Bruschetta",
        "description": "Pan tostado con tomate, albahaca y aceite de oliva",
        "weight": "150g",
        "price": 5.00,
        "category": "Entrantes"
    },
    {
        "name": "Croquetas de Jamón",
        "description": "Croquetas caseras de jamón serrano",
        "weight": "200g",
        "price": 6.50,
        "category": "Entrantes"
    },
    {
        "name": "Nachos con Queso",
        "description": "Nachos con queso fundido, guacamole y pico de gallo",
        "weight": "350g",
        "price": 8.00,
        "category": "Entrantes"
    },
    {
        "name": "Alitas Picantes",
        "description": "Alitas de pollo con salsa BBQ o buffalo",
        "weight": "300g",
        "price": 9.00,
        "category": "Entrantes"
    },
    # Platos principales (8 productos)
    {
        "name": "Filete de Res",
        "description": "Filete de res a la parrilla con papas y vegetales",
        "weight": "400g",
        "price": 18.00,
        "category": "Platos principales"
    },
    {
        "name": "Pollo al Horno",
        "description": "Pechuga de pollo al horno con hierbas aromáticas",
        "weight": "350g",
        "price": 12.00,
        "category": "Platos principales"
    },
    {
        "name": "Salmón a la Plancha",
        "description": "Filete de salmón con limón y mantequilla",
        "weight": "300g",
        "price": 16.00,
        "category": "Platos principales"
    },
    {
        "name": "Costillas BBQ",
        "description": "Costillas de cerdo con salsa barbecue",
        "weight": "500g",
        "price": 15.00,
        "category": "Platos principales"
    },
    {
        "name": "Paella Valenciana",
        "description": "Arroz con mariscos, pollo y azafrán",
        "weight": "450g",
        "price": 14.00,
        "category": "Platos principales"
    },
    {
        "name": "Hamburguesa Clásica",
        "description": "Hamburguesa de res con queso, lechuga y tomate",
        "weight": "350g",
        "price": 10.00,
        "category": "Platos principales"
    },
    {
        "name": "Tacos al Pastor",
        "description": "3 tacos con carne al pastor, piña y cilantro",
        "weight": "300g",
        "price": 9.00,
        "category": "Platos principales"
    },
    {
        "name": "Ramen de Cerdo",
        "description": "Sopa japonesa con fideos, cerdo y huevo",
        "weight": "500ml",
        "price": 11.00,
        "category": "Platos principales"
    },
    # Postres (5 productos)
    {
        "name": "Tiramisú",
        "description": "Postre italiano con café, mascarpone y cacao",
        "weight": "150g",
        "price": 6.50,
        "category": "Postres"
    },
    {
        "name": "Cheesecake",
        "description": "Tarta de queso con frutos rojos",
        "weight": "180g",
        "price": 7.00,
        "category": "Postres"
    },
    {
        "name": "Flan de Caramelo",
        "description": "Flan casero con caramelo líquido",
        "weight": "120g",
        "price": 4.50,
        "category": "Postres"
    },
    {
        "name": "Brownie con Helado",
        "description": "Brownie de chocolate caliente con helado de vainilla",
        "weight": "200g",
        "price": 6.00,
        "category": "Postres"
    },
    {
        "name": "Crème Brûlée",
        "description": "Crema francesa con azúcar caramelizada",
        "weight": "140g",
        "price": 7.50,
        "category": "Postres"
    },
    # Italiano (5 productos)
    {
        "name": "Pizza Margherita",
        "description": "Pizza con tomate, mozzarella y albahaca",
        "weight": "450g",
        "price": 10.00,
        "category": "Italiano"
    },
    {
        "name": "Pasta Carbonara",
        "description": "Pasta con panceta, huevo y parmesano",
        "weight": "350g",
        "price": 11.00,
        "category": "Italiano"
    },
    {
        "name": "Lasagna Bolognesa",
        "description": "Lasagna con carne, bechamel y queso",
        "weight": "400g",
        "price": 13.00,
        "category": "Italiano"
    },
    {
        "name": "Risotto de Hongos",
        "description": "Arroz cremoso con hongos porcini",
        "weight": "350g",
        "price": 12.00,
        "category": "Italiano"
    },
    {
        "name": "Ravioli de Ricotta",
        "description": "Ravioles rellenos de ricotta con salsa de tomate",
        "weight": "300g",
        "price": 11.50,
        "category": "Italiano"
    },
    # Cócteles (4 productos)
    {
        "name": "Mojito",
        "description": "Ron, menta, limón, azúcar y soda",
        "weight": "300ml",
        "price": 8.00,
        "category": "Cócteles"
    },
    {
        "name": "Piña Colada",
        "description": "Ron, piña, coco y hielo",
        "weight": "350ml",
        "price": 9.00,
        "category": "Cócteles"
    },
    {
        "name": "Margarita",
        "description": "Tequila, triple sec, limón y sal",
        "weight": "250ml",
        "price": 8.50,
        "category": "Cócteles"
    },
    {
        "name": "Daiquiri de Fresa",
        "description": "Ron, fresas, limón y azúcar",
        "weight": "300ml",
        "price": 9.50,
        "category": "Cócteles"
    },
    # Bebidas frías (4 productos)
    {
        "name": "Limonada Natural",
        "description": "Limonada fresca con hielo",
        "weight": "400ml",
        "price": 3.50,
        "category": "Bebidas frías"
    },
    {
        "name": "Batido de Fresa",
        "description": "Batido de fresa con leche y hielo",
        "weight": "400ml",
        "price": 5.00,
        "category": "Bebidas frías"
    },
    {
        "name": "Jugo de Naranja",
        "description": "Jugo de naranja recién exprimido",
        "weight": "350ml",
        "price": 4.00,
        "category": "Bebidas frías"
    },
    {
        "name": "Smoothie Tropical",
        "description": "Batido de mango, piña y maracuyá",
        "weight": "450ml",
        "price": 5.50,
        "category": "Bebidas frías"
    },
    # Bebidas calientes (4 productos)
    {
        "name": "Café Americano",
        "description": "Café negro recién preparado",
        "weight": "250ml",
        "price": 2.50,
        "category": "Bebidas calientes"
    },
    {
        "name": "Cappuccino",
        "description": "Espresso con leche espumada",
        "weight": "300ml",
        "price": 4.00,
        "category": "Bebidas calientes"
    },
    {
        "name": "Té Verde",
        "description": "Té verde natural con miel",
        "weight": "250ml",
        "price": 3.00,
        "category": "Bebidas calientes"
    },
    {
        "name": "Chocolate Caliente",
        "description": "Chocolate con leche y crema batida",
        "weight": "300ml",
        "price": 4.50,
        "category": "Bebidas calientes"
    },
]


async def main():
    """Agregar productos de muestra a la sucursal."""
    
    print(f"🔗 Conectando a MongoDB: {MONGODB_URL}")
    print(f"📚 Base de datos: {MONGODB_DATABASE}")
    
    # Conectar a MongoDB
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[MONGODB_DATABASE]
    
    print(f"\n🔍 Verificando sucursal {BRANCH_ID}...")
    
    # Verificar que la sucursal existe
    branch = await db.branches.find_one({"_id": BRANCH_ID})
    if not branch:
        print(f"❌ Error: Sucursal {BRANCH_ID} no encontrada")
        client.close()
        return
    
    print(f"✅ Sucursal encontrada: {branch['name']}")
    print(f"📍 Tipo: {branch.get('tipos', ['restaurante'])[0]}")
    
    # Obtener categorías de restaurante
    print("\n🔍 Obteniendo categorías...")
    categories = await db.product_categories.find(
        {"branchType": "restaurante"}
    ).to_list(length=100)
    
    if not categories:
        print("❌ No se encontraron categorías de restaurante")
        client.close()
        return
    
    # Crear mapa de categorías por nombre
    category_map = {cat["name"]: cat["_id"] for cat in categories}
    print(f"✅ Encontradas {len(categories)} categorías")
    
    # Insertar productos
    print(f"\n📦 Insertando {len(SAMPLE_PRODUCTS)} productos...")
    inserted_count = 0
    
    for product_data in SAMPLE_PRODUCTS:
        category_name = product_data["category"]
        category_id = category_map.get(category_name)
        
        if not category_id:
            print(f"⚠️  Categoría '{category_name}' no encontrada, saltando producto")
            continue
        
        product = {
            "_id": str(uuid4()),
            "branchId": BRANCH_ID,
            "name": product_data["name"],
            "description": product_data["description"],
            "weight": product_data["weight"],
            "price": product_data["price"],
            "currency": "USD",
            "image": f"products/default_{category_name.lower().replace(' ', '_')}.jpg",
            "availability": True,
            "categoryId": category_id,
            "createdAt": datetime.utcnow()
        }
        
        try:
            await db.products.insert_one(product)
            inserted_count += 1
            print(f"  ✓ {product_data['name']} ({category_name})")
        except Exception as e:
            print(f"  ✗ Error insertando {product_data['name']}: {e}")
    
    print(f"\n✅ Proceso completado: {inserted_count}/{len(SAMPLE_PRODUCTS)} productos insertados")
    
    # Mostrar resumen por categoría
    print("\n📊 Resumen por categoría:")
    for category_name in sorted(set(p["category"] for p in SAMPLE_PRODUCTS)):
        count = await db.products.count_documents({
            "branchId": BRANCH_ID,
            "categoryId": category_map.get(category_name)
        })
        print(f"  • {category_name}: {count} productos")
    
    # Total de productos en la sucursal
    total = await db.products.count_documents({"branchId": BRANCH_ID})
    print(f"\n🎉 Total de productos en la sucursal: {total}")
    
    client.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  SCRIPT DE INSERCIÓN DE PRODUCTOS DE MUESTRA")
    print("=" * 60)
    asyncio.run(main())
