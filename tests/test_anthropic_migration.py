"""
Pruebas end-to-end para la migración DeepSeek → Claude.

  .venv-validate/bin/python3 tests/test_anthropic_migration.py
"""

import asyncio
import time
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")


# ---------------------------------------------------------------------------
# Test 1 — llamada básica a Claude
# ---------------------------------------------------------------------------

def test_hola():
    import anthropic
    from core.config import settings

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=64,
        messages=[{"role": "user", "content": "Hola"}],
    )

    text = response.content[0].text.strip()
    print(f"  Claude: {text!r}")
    assert text, "Respuesta vacía"


# ---------------------------------------------------------------------------
# Test 2 — pipeline completo real: Claude + Qdrant + MongoDB
# ---------------------------------------------------------------------------

PIZZA_ID    = "69a71b38b1f4a6030323816d"
ESPAGUETI_ID = "69a72525b1f4a6030323817f"

async def _test_quiero_pizza_espaguetti():
    from clients.mongodb_client import connect_to_mongo
    from clients.qdrant_client import connect_to_qdrant
    from clients.gemini_client import connect_to_gemini
    from services.ai_rag_service import AiRagService

    await connect_to_mongo()
    await connect_to_qdrant()
    connect_to_gemini()

    svc = AiRagService()

    mensaje = "quiero pizza y espaguetti"

    t0 = time.perf_counter()
    intent  = await svc._analyze_intent(mensaje, history=[])
    context = await svc._execute_searches(intent.search_queries)
    final   = await svc._generate_final_response(
        message=mensaje, history=[], intent=intent, context=context
    )
    elapsed = time.perf_counter() - t0

    print(f"  response_type     : {final.response_type}")
    print(f"  confidence        : {final.confidence:.2f}")
    print(f"  ai_text           : {final.ai_text}")
    print(f"  suggested_products: {[s.product_id for s in (final.suggested_products or [])]}")
    print(f"  suggested_branches: {[s.branch_id for s in (final.suggested_branches or [])]}")
    print(f"  tiempo total      : {elapsed:.2f}s")

    product_ids_in_context = {str(p.get("id", "")) for p in context.products}
    suggested_ids = {s.product_id for s in (final.suggested_products or [])}

    assert final.response_type == "search_products", \
        f"Se esperaba search_products, llegó {final.response_type!r}"
    assert final.ai_text.strip(), "ai_text vacío"
    assert PIZZA_ID in product_ids_in_context, \
        f"Pizza Margarita ({PIZZA_ID}) no apareció en el contexto de búsqueda"
    assert ESPAGUETI_ID in product_ids_in_context, \
        f"Espagueti Bolognesa ({ESPAGUETI_ID}) no apareció en el contexto de búsqueda"
    assert any(PIZZA_ID in pid for pid in suggested_ids) or any(ESPAGUETI_ID in pid for pid in suggested_ids), \
        f"Claude no sugirió ninguno de los productos esperados: {suggested_ids}"


def test_quiero_pizza_espaguetti():
    asyncio.run(_test_quiero_pizza_espaguetti())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n=== test_hola ===")
    test_hola()
    print("  PASS")

    print("\n=== test_quiero_pizza_y_espaguetti ===")
    test_quiero_pizza_espaguetti()
    print("  PASS")

    print("\nTodos los tests pasaron.")
