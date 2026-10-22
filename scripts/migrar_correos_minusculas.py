"""Pasa a minúsculas los correos de `users` guardados con mayúsculas (A12).

Desde de48601 el login y el registro guardan y buscan el correo en minúsculas (la búsqueda
ya no distingue mayúsculas), pero las cuentas antiguas pueden tenerlas. Si dos cuentas
quedarían con el mismo correo no se toca ninguna de las dos: se listan para decidir a mano
cuál conservar.

Uso (MONGODB_URL del entorno; nunca una URL escrita aquí):
    python scripts/migrar_correos_minusculas.py            # solo informa
    python scripts/migrar_correos_minusculas.py --aplicar  # cambia los que no chocan
"""
import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def planificar(usuarios):
    """(cambios, choques): cambios = [(_id, correo_nuevo)]; choques = {correo: [_ids]}."""
    por_correo = defaultdict(list)
    for u in usuarios:
        correo = (u.get("email") or "").strip()
        if correo:
            por_correo[correo.lower()].append(u)

    cambios, choques = [], {}
    for normalizado, grupo in por_correo.items():
        if len(grupo) > 1:
            choques[normalizado] = [str(u["_id"]) for u in grupo]
            continue
        u = grupo[0]
        if u["email"] != normalizado:
            cambios.append((u["_id"], normalizado))
    return cambios, choques


async def main(aplicar: bool) -> None:
    from clients.mongodb_client import close_mongo_connection, connect_to_mongo, get_database

    await connect_to_mongo()
    try:
        users = get_database()["users"]
        usuarios = await users.find({"email": {"$type": "string"}}, {"email": 1}).to_list(None)
        cambios, choques = planificar(usuarios)

        print(f"Cuentas con correo: {len(usuarios)}")
        print(f"A pasar a minúsculas: {len(cambios)}")
        print(f"Choques (no se tocan, decidir a mano): {len(choques)}")
        for correo, ids in sorted(choques.items()):
            print(f"  {correo}: {', '.join(ids)}")

        if not aplicar:
            print("\nSolo informe. Repite con --aplicar para cambiarlos.")
            return
        for _id, correo in cambios:
            await users.update_one({"_id": _id}, {"$set": {"email": correo}})
        print(f"\nActualizadas: {len(cambios)}")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="hacer los cambios")
    asyncio.run(main(parser.parse_args().aplicar))
