"""
Test del subscription GraphQL real via WebSocket contra el servidor deployado en Railway.
Reproduce exactamente lo que hace el cliente iOS.

Ejecutar con:
    .venv-validate/bin/python3 tests/test_graphql_streaming.py
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

BACKEND_WS_URL = "wss://llegobackend-production.up.railway.app/graphql"


def _get_real_user_id() -> str:
    """Fetch a real user _id from MongoDB to pass quota checks."""
    from pymongo import MongoClient
    client = MongoClient(os.environ["MONGODB_URL"])
    db = client[os.environ.get("MONGODB_DATABASE", "llego")]
    user = db["users"].find_one({}, {"_id": 1})
    client.close()
    if not user:
        raise RuntimeError("No hay usuarios en la base de datos")
    return str(user["_id"])


def _make_jwt(user_id: str) -> str:
    from jose import jwt as jose_jwt
    secret = os.environ["JWT_SECRET"]
    payload = {
        "user_id": user_id,
        "role": "user",
        "exp": datetime.utcnow() + timedelta(days=1),
    }
    return jose_jwt.encode(payload, secret, algorithm="HS256")


SUBSCRIPTION = """
subscription($input: AiAssistantChatInput!, $jwt: String) {
  aiChatStream(input: $input, jwt: $jwt) {
    delta
    accumulatedText
    isFinal
    suggestedProductIds
    suggestedBranchIds
    confidence
    error { code message }
  }
}
"""


async def run():
    import websockets

    print("  Buscando usuario real en MongoDB...")
    user_id = _get_real_user_id()
    print(f"  user_id: {user_id}")
    jwt = _make_jwt(user_id)

    print(f"  Conectando a {BACKEND_WS_URL} ...")

    async with websockets.connect(
        BACKEND_WS_URL,
        subprotocols=["graphql-transport-ws"],
        open_timeout=15,
    ) as ws:

        # 1. Inicializar conexión
        await ws.send(json.dumps({"type": "connection_init", "payload": {}}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        assert msg["type"] == "connection_ack", f"Esperaba connection_ack, recibí: {msg}"
        print("  connection_ack ✓\n")
        print("  Respuesta de Claude:")
        print("  " + "-" * 60)

        # 2. Enviar subscription
        await ws.send(json.dumps({
            "type": "subscribe",
            "id": "1",
            "payload": {
                "query": SUBSCRIPTION,
                "variables": {
                    "input": {
                        "message": "comida italiana con carne",
                        "stream": True,
                        "deviceId": "test-device-streaming-001",
                    },
                    "jwt": jwt,
                },
            },
        }))

        t0 = time.perf_counter()
        accumulated = ""
        product_ids = []
        branch_ids = []
        chunk_count = 0

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=120)
            msg = json.loads(raw)

            if msg["type"] == "next":
                chunk = msg["payload"]["data"]["aiChatStream"]

                if chunk.get("error"):
                    print(f"\n\n  ERROR del servidor: {chunk['error']}")
                    break

                delta = chunk.get("delta", "")
                if delta:
                    print(delta, end="", flush=True)
                    chunk_count += 1

                if chunk.get("isFinal"):
                    accumulated = chunk.get("accumulatedText", "")
                    product_ids = chunk.get("suggestedProductIds") or []
                    branch_ids = chunk.get("suggestedBranchIds") or []
                    break

            elif msg["type"] == "complete":
                print("\n  (stream completado sin chunk isFinal)")
                break

            elif msg["type"] == "error":
                print(f"\n  ERROR WS: {msg.get('payload')}")
                break

        elapsed = time.perf_counter() - t0

        print(f"\n  " + "-" * 60)
        print(f"  Chunks de texto   : {chunk_count}")
        print(f"  Texto completo    :\n    {accumulated!r}")
        print(f"  Product IDs       : {product_ids}")
        print(f"  Branch IDs        : {branch_ids}")
        print(f"  Tiempo total      : {elapsed:.2f}s")

        assert accumulated.strip(), "accumulatedText vacío — el texto llegó cortado o vacío"
        assert chunk_count > 0, "No se recibió ningún chunk de texto"

        print("\n  PASS ✓")


if __name__ == "__main__":
    print("\n=== test_graphql_streaming: comida italiana con carne ===")
    asyncio.run(run())
