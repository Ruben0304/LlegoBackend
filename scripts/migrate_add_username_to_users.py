"""
Script de migración para agregar username a usuarios existentes.

Este script genera usernames únicos para todos los usuarios que no lo tengan,
basándose en la parte antes del @ de su email.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate_add_username():
    """Agrega username a usuarios que no lo tengan."""
    
    # Conectar a MongoDB
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "llego")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[database_name]
    
    print("🔄 Iniciando migración de usernames...")
    
    # Obtener usuarios sin username
    users_collection = db["users"]
    users_without_username = await users_collection.count_documents({
        "username": {"$exists": False}
    })
    
    if users_without_username == 0:
        print("   ✓ Todos los usuarios ya tienen username")
        client.close()
        return
    
    print(f"   Encontrados {users_without_username} usuarios sin username")
    
    # Procesar cada usuario
    cursor = users_collection.find({"username": {"$exists": False}})
    updated_count = 0
    
    async for user in cursor:
        email = user.get("email", "")
        if not email:
            print(f"   ⚠ Usuario {user['_id']} no tiene email, saltando...")
            continue
        
        # Generar username base del email
        base_username = email.split("@")[0]
        username = base_username
        
        # Asegurar que sea único
        counter = 1
        while await users_collection.find_one({"username": username}):
            username = f"{base_username}{counter}"
            counter += 1
        
        # Actualizar usuario
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"username": username}}
        )
        updated_count += 1
        print(f"   ✓ Usuario {email} -> username: {username}")
    
    print(f"   ✓ Actualizados {updated_count} usuarios")
    
    # Crear índice único para username
    try:
        await users_collection.create_index("username", unique=True)
        print("   ✓ Índice único creado para username")
    except Exception as e:
        print(f"   ⚠ Error creando índice: {e}")
    
    # Cerrar conexión
    client.close()
    print("✓ Migración de usernames completada\n")


async def migrate_add_username_from_db(db):
    """
    Versión de la migración que usa una conexión de base de datos existente.
    
    Args:
        db: Instancia de base de datos de MongoDB ya conectada
    """
    print("🔄 Iniciando migración de usernames...")
    
    # Obtener usuarios sin username
    users_collection = db["users"]
    users_without_username = await users_collection.count_documents({
        "username": {"$exists": False}
    })
    
    if users_without_username == 0:
        print("   ✓ Todos los usuarios ya tienen username")
        return
    
    print(f"   Encontrados {users_without_username} usuarios sin username")
    
    # Procesar cada usuario
    cursor = users_collection.find({"username": {"$exists": False}})
    updated_count = 0
    
    async for user in cursor:
        email = user.get("email", "")
        if not email:
            print(f"   ⚠ Usuario {user['_id']} no tiene email, saltando...")
            continue
        
        # Generar username base del email
        base_username = email.split("@")[0]
        username = base_username
        
        # Asegurar que sea único
        counter = 1
        while await users_collection.find_one({"username": username}):
            username = f"{base_username}{counter}"
            counter += 1
        
        # Actualizar usuario
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"username": username}}
        )
        updated_count += 1
        print(f"   ✓ Usuario {email} -> username: {username}")
    
    print(f"   ✓ Actualizados {updated_count} usuarios")
    
    # Crear índice único para username
    try:
        await users_collection.create_index("username", unique=True)
        print("   ✓ Índice único creado para username")
    except Exception as e:
        print(f"   ⚠ Error creando índice: {e}")
    
    print("✓ Migración de usernames completada\n")


if __name__ == "__main__":
    # Ejecutar migración de forma independiente
    asyncio.run(migrate_add_username())
