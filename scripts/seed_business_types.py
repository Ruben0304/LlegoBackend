"""Seed script for business type configurations."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from clients import get_database

BUSINESS_TYPE_CONFIGS = [
    {
        "_id": "bt_restaurante",
        "key": "RESTAURANTE",
        "name": "Restaurantes",
        "description": "Comida y Bebidas",
        "icon": "fork.knife",
        "model3dFileName": "restaurant.usdz",
        "model3dUrl": None,
        "model3dVersion": 1,
        "glowColor": "#E64D33",
        "gradient": {
            "darkColor": "#801A19",
            "mediumColor": "#B34026",
            "lightColor": "#D9734D",
            "veryLightColor": "#F2E0D9",
            "overlayColor": "#731E14",
        },
        "camera": {
            "positionX": 0.0,
            "positionY": 4.0,
            "positionZ": 0.0,
            "eulerX": -1.5708,
            "eulerY": 0.0,
            "eulerZ": 0.0,
        },
        "features": [
            {
                "icon": "fork.knife",
                "title": "Gourmet",
                "subtitle": "Alta cocina",
                "sortOrder": 0,
            },
            {
                "icon": "flame.fill",
                "title": "Fast Food",
                "subtitle": "Hamburguesas",
                "sortOrder": 1,
            },
            {
                "icon": "fish.fill",
                "title": "Sushi & Mar",
                "subtitle": "Fresco del día",
                "sortOrder": 2,
            },
            {
                "icon": "birthday.cake.fill",
                "title": "Postres",
                "subtitle": "Dulces momentos",
                "sortOrder": 3,
            },
            {
                "icon": "wineglass.fill",
                "title": "Bebidas",
                "subtitle": "Coctelería",
                "sortOrder": 4,
            },
        ],
        "sortOrder": 0,
        "isActive": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": "bt_tienda",
        "key": "TIENDA",
        "name": "Tiendas",
        "description": "Productos del Hogar",
        "icon": "cart.fill",
        "model3dFileName": "mercadito.usdz",
        "model3dUrl": None,
        "model3dVersion": 1,
        "glowColor": "#33B380",
        "gradient": {
            "darkColor": "#0D4D40",
            "mediumColor": "#1A7361",
            "lightColor": "#66A68C",
            "veryLightColor": "#D9EBE0",
            "overlayColor": "#0D4033",
        },
        "camera": {
            "positionX": 0.0,
            "positionY": 0.0,
            "positionZ": 3.2,
            "eulerX": None,
            "eulerY": None,
            "eulerZ": None,
        },
        "features": [
            {
                "icon": "carrot.fill",
                "title": "Frescos",
                "subtitle": "Frutas y verduras",
                "sortOrder": 0,
            },
            {
                "icon": "cart.fill",
                "title": "Despensa",
                "subtitle": "Básicos del hogar",
                "sortOrder": 1,
            },
            {
                "icon": "drop.fill",
                "title": "Bebidas",
                "subtitle": "Jugos y refrescos",
                "sortOrder": 2,
            },
            {
                "icon": "house.fill",
                "title": "Hogar",
                "subtitle": "Limpieza y más",
                "sortOrder": 3,
            },
            {
                "icon": "heart.fill",
                "title": "Cuidado",
                "subtitle": "Personal",
                "sortOrder": 4,
            },
        ],
        "sortOrder": 1,
        "isActive": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "_id": "bt_dulceria",
        "key": "DULCERIA",
        "name": "Dulcería",
        "description": "Pan y Repostería",
        "icon": "birthday.cake.fill",
        "model3dFileName": "dulce.usdz",
        "model3dUrl": "https://tu-bucket.s3.amazonaws.com/models/dulce.usdz",
        "model3dVersion": 1,
        "glowColor": "#BC8358",
        "gradient": {
            "darkColor": "#BC8358",
            "mediumColor": "#E8CBB3",
            "lightColor": "#D9B399",
            "veryLightColor": "#F5EBE0",
            "overlayColor": "#A6734D",
        },
        "camera": {
            "positionX": 0.0,
            "positionY": 0.0,
            "positionZ": 3.2,
            "eulerX": None,
            "eulerY": None,
            "eulerZ": None,
        },
        "features": [
            {
                "icon": "birthday.cake.fill",
                "title": "Pasteles",
                "subtitle": "Recién horneados",
                "sortOrder": 0,
            },
            {
                "icon": "cup.and.saucer.fill",
                "title": "Pan Dulce",
                "subtitle": "Tradicional",
                "sortOrder": 1,
            },
            {
                "icon": "gift.fill",
                "title": "Chocolates",
                "subtitle": "Premium",
                "sortOrder": 2,
            },
            {
                "icon": "sparkles",
                "title": "Galletas",
                "subtitle": "Artesanales",
                "sortOrder": 3,
            },
            {
                "icon": "star.fill",
                "title": "Especiales",
                "subtitle": "Del día",
                "sortOrder": 4,
            },
        ],
        "sortOrder": 2,
        "isActive": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
]


async def seed_business_types_from_db(db):
    """
    Seed business type configurations into the database.

    Args:
        db: MongoDB database instance

    Returns:
        bool: True if seeding was performed, False if skipped
    """
    collection = db["business_type_configs"]

    # Check if already seeded
    existing_count = await collection.count_documents({})
    if existing_count > 0:
        print(
            f"ℹ Business types already exist ({existing_count} found). Skipping seed."
        )
        return False

    print("🌱 Seeding business type configurations...")

    for config in BUSINESS_TYPE_CONFIGS:
        await collection.insert_one(config)
        print(f"  ✅ Created {config['name']}")

    print("✨ Business type configurations seeded successfully!")
    return True


async def seed_business_types():
    """Standalone function to seed business types (for manual execution)."""
    db = get_database()
    collection = db["business_type_configs"]

    print("🌱 Seeding business type configurations...")

    for config in BUSINESS_TYPE_CONFIGS:
        # Check if already exists
        existing = await collection.find_one({"_id": config["_id"]})

        if existing:
            print(f"  ⏭️  {config['name']} already exists, skipping...")
        else:
            await collection.insert_one(config)
            print(f"  ✅ Created {config['name']}")

    print("✨ Business type configurations seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_business_types())
