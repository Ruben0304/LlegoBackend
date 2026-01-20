"""
Script de migración para agregar wallet a usuarios y branches que no lo tengan.

Este script se ejecuta automáticamente al iniciar el backend y agrega el objeto wallet
con valores iniciales de 0 a todos los usuarios y branches que no lo tengan definido.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate_add_wallet():
    """Agrega wallet a usuarios y branches que no lo tengan."""
    
    # Conectar a MongoDB
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "llego")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[database_name]
    
    print("🔄 Iniciando migración de wallets...")
    
    # Migrar usuarios
    users_collection = db["users"]
    users_without_wallet = await users_collection.count_documents({
        "$or": [
            {"wallet": {"$exists": False}},
            {"walletStatus": {"$exists": False}}
        ]
    })
    
    if users_without_wallet > 0:
        print(f"   Encontrados {users_without_wallet} usuarios sin wallet")
        result = await users_collection.update_many(
            {
                "$or": [
                    {"wallet": {"$exists": False}},
                    {"walletStatus": {"$exists": False}}
                ]
            },
            {
                "$set": {
                    "wallet": {"local": 0.0, "usd": 0.0},
                    "walletStatus": "active"
                }
            }
        )
        print(f"   ✓ Actualizados {result.modified_count} usuarios")
    else:
        print("   ✓ Todos los usuarios ya tienen wallet")
    
    # Migrar branches
    branches_collection = db["branches"]
    branches_without_wallet = await branches_collection.count_documents({
        "$or": [
            {"wallet": {"$exists": False}},
            {"walletStatus": {"$exists": False}}
        ]
    })
    
    if branches_without_wallet > 0:
        print(f"   Encontradas {branches_without_wallet} sucursales sin wallet")
        result = await branches_collection.update_many(
            {
                "$or": [
                    {"wallet": {"$exists": False}},
                    {"walletStatus": {"$exists": False}}
                ]
            },
            {
                "$set": {
                    "wallet": {"local": 0.0, "usd": 0.0},
                    "walletStatus": "active"
                }
            }
        )
        print(f"   ✓ Actualizadas {result.modified_count} sucursales")
    else:
        print("   ✓ Todas las sucursales ya tienen wallet")
    
    # Cerrar conexión
    client.close()
    print("✓ Migración de wallets completada\n")


async def migrate_add_wallet_from_db(db):
    """
    Versión de la migración que usa una conexión de base de datos existente.
    
    Args:
        db: Instancia de base de datos de MongoDB ya conectada
    """
    print("🔄 Iniciando migración de wallets...")
    
    # Migrar usuarios
    users_collection = db["users"]
    users_without_wallet = await users_collection.count_documents({
        "$or": [
            {"wallet": {"$exists": False}},
            {"walletStatus": {"$exists": False}}
        ]
    })
    
    if users_without_wallet > 0:
        print(f"   Encontrados {users_without_wallet} usuarios sin wallet")
        result = await users_collection.update_many(
            {
                "$or": [
                    {"wallet": {"$exists": False}},
                    {"walletStatus": {"$exists": False}}
                ]
            },
            {
                "$set": {
                    "wallet": {"local": 0.0, "usd": 0.0},
                    "walletStatus": "active"
                }
            }
        )
        print(f"   ✓ Actualizados {result.modified_count} usuarios")
    else:
        print("   ✓ Todos los usuarios ya tienen wallet")
    
    # Migrar branches
    branches_collection = db["branches"]
    branches_without_wallet = await branches_collection.count_documents({
        "$or": [
            {"wallet": {"$exists": False}},
            {"walletStatus": {"$exists": False}}
        ]
    })
    
    if branches_without_wallet > 0:
        print(f"   Encontradas {branches_without_wallet} sucursales sin wallet")
        result = await branches_collection.update_many(
            {
                "$or": [
                    {"wallet": {"$exists": False}},
                    {"walletStatus": {"$exists": False}}
                ]
            },
            {
                "$set": {
                    "wallet": {"local": 0.0, "usd": 0.0},
                    "walletStatus": "active"
                }
            }
        )
        print(f"   ✓ Actualizadas {result.modified_count} sucursales")
    else:
        print("   ✓ Todas las sucursales ya tienen wallet")
    
    print("✓ Migración de wallets completada\n")


if __name__ == "__main__":
    # Ejecutar migración de forma independiente
    asyncio.run(migrate_add_wallet())
