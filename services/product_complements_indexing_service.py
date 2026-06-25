"""Nightly product-complements indexing with Claude Sonnet via the Batch API.

For every product in a store, Claude precomputes a short ranked list of OTHER
products from the SAME store that complement it (cross-sell). The result is
stored per product in MongoDB so the cart recommender can serve from it at
request time with NO live LLM call.

- Model: latest Sonnet (claude-sonnet-4-6).
- Batch API (50% cheaper, async) — this runs offline at night, not on the
  request path.
- Only re-indexes stores whose product set changed since the last run
  (additions or deletions), detected via a per-branch product-id hash.
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from pymongo import UpdateOne

from clients import get_database
from core.config import settings

# Latest Sonnet at the moment. Bump this when a newer Sonnet ships.
SONNET_MODEL = "claude-sonnet-4-6"

COMPLEMENTS_COLLECTION = "product_complements"
STATE_COLLECTION = "recommendation_index_state"

MAX_MENU = 120  # cap candidate names per product prompt (huge catalogs)
COMPLEMENTS_PER_PRODUCT = 8  # how many complements to keep per product
POLL_INTERVAL_SECONDS = 30
MAX_WAIT_SECONDS = 3 * 3600  # safety cap waiting for the batch to finish

_SYSTEM_PROMPT = (
    "Eres el asistente de ventas de Llego. Para un producto dado, eliges de una "
    "lista numerada de OTROS productos de la misma tienda los que mejor lo "
    "COMPLEMENTAN para subir el ticket (bebida, acompañante, postre, salsa, "
    "extra que combine). NUNCA elijas sustitutos ni más de lo mismo: para una "
    "hamburguesa de res eliges una bebida o unas papas, NO otra hamburguesa ni "
    "otro plato de res. Ordenas de la opción que mejor pega a la que menos. "
    "Respondes SOLO con el JSON pedido, sin markdown."
)


class ProductComplementsIndexingService:
    """Precomputes per-product complements with Sonnet (Batch API)."""

    def __init__(self):
        if not settings.anthropic_api_key:
            print("⚠ Anthropic key missing — complements indexing disabled.")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # ------------------------------------------------------------------ #
    # Entry point (called by the nightly worker)
    # ------------------------------------------------------------------ #
    async def run_nightly(self) -> Dict[str, Any]:
        if not self.client:
            return {"skipped": "no_anthropic_key"}

        db = get_database()
        branches = await self._load_branches_with_products(db)
        changed = await self._select_changed_branches(db, branches)

        print(
            f"🌙 [complements] branches con productos: {len(branches)} | "
            f"cambiadas desde el último cron: {len(changed)}"
        )
        if not changed:
            return {"branches_changed": 0, "products_indexed": 0}

        requests, meta = self._build_requests(branches, changed)
        if not requests:
            await self._save_state(db, branches, changed)
            return {"branches_changed": len(changed), "products_indexed": 0}

        print(f"🌙 [complements] enviando batch con {len(requests)} productos...")
        indexed = await self._run_batch_and_store(db, requests, meta)
        await self._save_state(db, branches, changed)
        return {"branches_changed": len(changed), "products_indexed": indexed}

    # ------------------------------------------------------------------ #
    # Change detection
    # ------------------------------------------------------------------ #
    async def _load_branches_with_products(
        self, db
    ) -> Dict[str, List[Dict[str, Any]]]:
        cursor = db["products"].find(
            {}, {"_id": 1, "branchId": 1, "name": 1, "availability": 1}
        )
        docs = await cursor.to_list(length=None)
        branches: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            branch_id = str(d.get("branchId"))
            if not branch_id or branch_id == "None":
                continue
            branches.setdefault(branch_id, []).append(
                {
                    "id": str(d["_id"]),
                    "name": (d.get("name") or "").strip(),
                    "availability": d.get("availability", True),
                }
            )
        return branches

    @staticmethod
    def _branch_hash(products: List[Dict[str, Any]]) -> str:
        ids = sorted(p["id"] for p in products)
        return hashlib.sha1("|".join(ids).encode("utf-8")).hexdigest()

    async def _select_changed_branches(
        self, db, branches: Dict[str, List[Dict[str, Any]]]
    ) -> List[str]:
        state_docs = await db[STATE_COLLECTION].find({}).to_list(length=None)
        prev = {s["_id"]: s.get("productIdsHash") for s in state_docs}
        changed = []
        for branch_id, products in branches.items():
            if prev.get(branch_id) != self._branch_hash(products):
                changed.append(branch_id)
        return changed

    # ------------------------------------------------------------------ #
    # Batch building
    # ------------------------------------------------------------------ #
    def _build_requests(
        self, branches: Dict[str, List[Dict[str, Any]]], changed: List[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        requests: List[Dict[str, Any]] = []
        meta: Dict[str, Dict[str, Any]] = {}

        for branch_id in changed:
            products = branches.get(branch_id, [])
            if len(products) < 2:
                continue  # need at least one candidate to complement with
            for product in products:
                candidates = [p for p in products if p["id"] != product["id"]][
                    :MAX_MENU
                ]
                if not candidates:
                    continue
                custom_id = product["id"]
                meta[custom_id] = {
                    "branchId": branch_id,
                    "candidate_ids": [c["id"] for c in candidates],
                }
                user_prompt = self._build_user_prompt(product["name"], candidates)
                requests.append(
                    {
                        "custom_id": custom_id,
                        "params": {
                            "model": SONNET_MODEL,
                            "max_tokens": 500,
                            "system": _SYSTEM_PROMPT,
                            "messages": [{"role": "user", "content": user_prompt}],
                        },
                    }
                )
        return requests, meta

    def _build_user_prompt(
        self, product_name: str, candidates: List[Dict[str, Any]]
    ) -> str:
        options = "\n".join(
            f"{i}. {c['name']}" for i, c in enumerate(candidates, start=1)
        )
        return (
            f"PRODUCTO: {product_name}\n\n"
            f"OPCIONES (elige por número):\n{options}\n\n"
            f"Elige hasta {COMPLEMENTS_PER_PRODUCT} opciones que COMPLEMENTEN a "
            "este producto (bebida, acompañante, postre o extra que combine), de "
            "la que mejor pega a la que menos. Evita sustitutos y duplicados del "
            'mismo tipo. Si nada complementa bien, devuelve "picks": [].\n\n'
            "Responde SOLO con este JSON, sin markdown:\n"
            '{"picks": [{"n": <numero de la opcion>, "why": "por qué pega, breve"}]}'
        )

    # ------------------------------------------------------------------ #
    # Batch submit + poll + store
    # ------------------------------------------------------------------ #
    async def _run_batch_and_store(
        self, db, requests: List[Dict[str, Any]], meta: Dict[str, Dict[str, Any]]
    ) -> int:
        batch = await asyncio.to_thread(
            self.client.messages.batches.create, requests=requests
        )
        print(f"🌙 [complements] batch creado: {batch.id} ({batch.processing_status})")

        # Poll until the batch finishes (offline job — it can afford to wait).
        start = time.time()
        while True:
            current = await asyncio.to_thread(
                self.client.messages.batches.retrieve, batch.id
            )
            if current.processing_status == "ended":
                break
            if time.time() - start > MAX_WAIT_SECONDS:
                raise TimeoutError(f"Batch {batch.id} no terminó en el límite")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        print(
            f"🌙 [complements] batch terminado. Conteos: {current.request_counts}"
        )

        results = await asyncio.to_thread(
            lambda: list(self.client.messages.batches.results(batch.id))
        )

        now = datetime.utcnow()
        ops: List[UpdateOne] = []
        for result in results:
            if result.result.type != "succeeded":
                continue
            info = meta.get(result.custom_id)
            if not info:
                continue
            message = result.result.message
            text = "".join(
                b.text for b in message.content if b.type == "text"
            ).strip()
            complements = self._parse_picks(text, info["candidate_ids"])
            ops.append(
                UpdateOne(
                    {"_id": result.custom_id},
                    {
                        "$set": {
                            "branchId": info["branchId"],
                            "complements": complements,
                            "model": SONNET_MODEL,
                            "updatedAt": now,
                        }
                    },
                    upsert=True,
                )
            )

        if ops:
            await db[COMPLEMENTS_COLLECTION].bulk_write(ops, ordered=False)
        return len(ops)

    @staticmethod
    def _parse_picks(text: str, candidate_ids: List[str]) -> List[Dict[str, Any]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            return []

        picks = data.get("picks") or []
        out: List[Dict[str, Any]] = []
        seen = set()
        for rank, pick in enumerate(picks):
            try:
                n = int(pick.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            idx = n - 1
            if idx < 0 or idx >= len(candidate_ids) or idx in seen:
                continue
            seen.add(idx)
            out.append(
                {
                    "productId": candidate_ids[idx],
                    "reason": str(pick.get("why", "")).strip(),
                    # Rank-based score so the cart merge can weight by position.
                    "score": round(max(0.1, 1.0 - rank * 0.12), 3),
                }
            )
            if len(out) >= COMPLEMENTS_PER_PRODUCT:
                break
        return out

    async def _save_state(
        self, db, branches: Dict[str, List[Dict[str, Any]]], changed: List[str]
    ) -> None:
        now = datetime.utcnow()
        ops = [
            UpdateOne(
                {"_id": branch_id},
                {
                    "$set": {
                        "productIdsHash": self._branch_hash(branches[branch_id]),
                        "productCount": len(branches[branch_id]),
                        "updatedAt": now,
                    }
                },
                upsert=True,
            )
            for branch_id in changed
            if branch_id in branches
        ]
        if ops:
            await db[STATE_COLLECTION].bulk_write(ops, ordered=False)


# Singleton instance
product_complements_indexing_service = ProductComplementsIndexingService()
