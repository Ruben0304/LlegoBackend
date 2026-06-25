"""Incremental nightly product-complements indexing (Claude Sonnet + Batch API).

Instead of re-indexing a whole store when anything changes, this only touches
the DELTA since the last run:

- Deleted product   -> NO LLM. `$pull` its id from every sibling's complement
                       list and delete its own doc.
- Added / changed   -> ONE LLM call (in the batch) per product, with the full
  product            store catalog as context. The model returns two things in the
                     same response:
                       (a) `own`     -> the complements *for* this product, and
                       (b) `host_of` -> the products this one should be added to
                                        as a complement (with a strength), only
                                        if it objectively fits.
                     We write the product's own doc and append it into each host's
                     list (insert by score, re-sort, cap) — no second call.

Model: latest Sonnet (claude-sonnet-4-6). Batch API (50% cheaper, offline).
Runtime (cart) never calls the LLM — it just reads `product_complements`.
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

# Latest Sonnet at the moment. Bump when a newer Sonnet ships.
SONNET_MODEL = "claude-sonnet-4-6"

COMPLEMENTS_COLLECTION = "product_complements"
STATE_COLLECTION = "recommendation_index_state"

MAX_MENU = 120  # cap catalog names per prompt (huge catalogs)
COMPLEMENTS_PER_PRODUCT = 8  # max complements stored per product
POLL_INTERVAL_SECONDS = 30
MAX_WAIT_SECONDS = 3 * 3600

_SYSTEM_PROMPT = (
    "Eres el asistente de ventas de Llego. Trabajas con complementariedad para "
    "subir el ticket: qué productos pegan juntos (bebida, acompañante, postre, "
    "salsa, extra). NUNCA trates como complemento a un sustituto o más de lo "
    "mismo: para una hamburguesa de res, una bebida o unas papas SÍ; otra "
    "hamburguesa u otro plato de res NO. Respondes SOLO con el JSON pedido, "
    "sin markdown."
)


class ProductComplementsIndexingService:
    """Incremental per-product complements indexing with Sonnet (Batch API)."""

    def __init__(self):
        if not settings.anthropic_api_key:
            print("⚠ Anthropic key missing — complements indexing disabled.")
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # ------------------------------------------------------------------ #
    # Entry point (nightly worker)
    # ------------------------------------------------------------------ #
    async def run_nightly(self) -> Dict[str, Any]:
        if not self.client:
            return {"skipped": "no_anthropic_key"}

        db = get_database()
        branches = await self._load_branches_with_products(db)
        state = await self._load_state(db)

        removed, targets, changed_by_branch = self._diff(branches, state)

        print(
            f"🌙 [complements] borrados={sum(len(v) for v in removed.values())} | "
            f"añadidos/cambiados={len(targets)}"
        )

        # 1) Deletions — no LLM.
        if removed:
            await self._apply_deletions(db, removed)

        # 2) Changed products: clear their stale entries from siblings before re-add.
        if changed_by_branch:
            await self._prepull_changed(db, changed_by_branch)

        # 3) Added/changed products: one batch call each (forward + backward).
        indexed = 0
        if targets:
            requests, meta = self._build_delta_requests(branches, targets)
            if requests:
                print(f"🌙 [complements] batch con {len(requests)} productos...")
                indexed = await self._run_batch_and_apply(db, requests, meta)

        # 4) Persist current per-product fingerprints.
        await self._save_state(db, branches, set(state.keys()))

        return {
            "deleted": sum(len(v) for v in removed.values()),
            "indexed": indexed,
        }

    # ------------------------------------------------------------------ #
    # Load + diff
    # ------------------------------------------------------------------ #
    async def _load_branches_with_products(
        self, db
    ) -> Dict[str, List[Dict[str, Any]]]:
        cursor = db["products"].find({}, {"_id": 1, "branchId": 1, "name": 1})
        docs = await cursor.to_list(length=None)
        branches: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            branch_id = str(d.get("branchId"))
            if not branch_id or branch_id == "None":
                continue
            branches.setdefault(branch_id, []).append(
                {"id": str(d["_id"]), "name": (d.get("name") or "").strip()}
            )
        return branches

    async def _load_state(self, db) -> Dict[str, Dict[str, Any]]:
        docs = await db[STATE_COLLECTION].find({}).to_list(length=None)
        return {
            d["_id"]: {
                "fp": d.get("productsFp") or {},
                # back-compat with the first (full-reindex) version's state
                "hash": d.get("productIdsHash"),
            }
            for d in docs
        }

    @staticmethod
    def _fingerprint(name: str) -> str:
        return hashlib.sha1((name or "").strip().lower().encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _branch_hash(products: List[Dict[str, Any]]) -> str:
        ids = sorted(p["id"] for p in products)
        return hashlib.sha1("|".join(ids).encode("utf-8")).hexdigest()

    def _diff(
        self,
        branches: Dict[str, List[Dict[str, Any]]],
        state: Dict[str, Dict[str, Any]],
    ) -> Tuple[Dict[str, List[str]], List[Tuple[str, str]], Dict[str, List[str]]]:
        removed: Dict[str, List[str]] = {}
        targets: List[Tuple[str, str]] = []  # (branchId, productId) added or changed
        changed_by_branch: Dict[str, List[str]] = {}

        for branch_id in set(branches) | set(state):
            products = branches.get(branch_id, [])
            cur_fp = {p["id"]: self._fingerprint(p["name"]) for p in products}
            st = state.get(branch_id, {})
            prev_fp: Dict[str, str] = st.get("fp") or {}
            prev_hash: Optional[str] = st.get("hash")

            # Migration from the old (hash-only) state format.
            if not prev_fp and prev_hash is not None:
                if prev_hash == self._branch_hash(products):
                    continue  # unchanged — just migrate fingerprints in _save_state
                # changed but no per-product info → reindex present products
                targets.extend((branch_id, pid) for pid in cur_fp)
                continue

            rem = [pid for pid in prev_fp if pid not in cur_fp]
            if rem:
                removed[branch_id] = rem
            for pid, fp in cur_fp.items():
                if pid not in prev_fp:
                    targets.append((branch_id, pid))  # added
                elif prev_fp[pid] != fp:
                    targets.append((branch_id, pid))  # changed
                    changed_by_branch.setdefault(branch_id, []).append(pid)

        return removed, targets, changed_by_branch

    # ------------------------------------------------------------------ #
    # Cheap, no-LLM ops
    # ------------------------------------------------------------------ #
    async def _apply_deletions(self, db, removed: Dict[str, List[str]]) -> None:
        coll = db[COMPLEMENTS_COLLECTION]
        for branch_id, ids in removed.items():
            # remove the deleted products from every sibling's complement list
            await coll.update_many(
                {"branchId": branch_id},
                {"$pull": {"complements": {"productId": {"$in": ids}}}},
            )
            # drop their own docs
            await coll.delete_many({"_id": {"$in": ids}})

    async def _prepull_changed(self, db, changed_by_branch: Dict[str, List[str]]) -> None:
        coll = db[COMPLEMENTS_COLLECTION]
        for branch_id, ids in changed_by_branch.items():
            await coll.update_many(
                {"branchId": branch_id},
                {"$pull": {"complements": {"productId": {"$in": ids}}}},
            )

    # ------------------------------------------------------------------ #
    # Batch building (one request per added/changed product)
    # ------------------------------------------------------------------ #
    def _build_delta_requests(
        self, branches: Dict[str, List[Dict[str, Any]]], targets: List[Tuple[str, str]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        by_branch = {
            b: {p["id"]: p for p in prods} for b, prods in branches.items()
        }
        requests: List[Dict[str, Any]] = []
        meta: Dict[str, Dict[str, Any]] = {}

        for branch_id, product_id in targets:
            products = branches.get(branch_id, [])
            target = by_branch.get(branch_id, {}).get(product_id)
            if not target or len(products) < 2:
                continue
            candidates = [p for p in products if p["id"] != product_id][:MAX_MENU]
            if not candidates:
                continue
            meta[product_id] = {
                "branchId": branch_id,
                "candidate_ids": [c["id"] for c in candidates],
            }
            requests.append(
                {
                    "custom_id": product_id,
                    "params": {
                        "model": SONNET_MODEL,
                        "max_tokens": 700,
                        "system": _SYSTEM_PROMPT,
                        "messages": [
                            {
                                "role": "user",
                                "content": self._build_delta_prompt(
                                    target["name"], candidates
                                ),
                            }
                        ],
                    },
                }
            )
        return requests, meta

    def _build_delta_prompt(
        self, product_name: str, candidates: List[Dict[str, Any]]
    ) -> str:
        options = "\n".join(
            f"{i}. {c['name']}" for i, c in enumerate(candidates, start=1)
        )
        return (
            f'PRODUCTO: "{product_name}"\n\n'
            f"CATÁLOGO DE LA TIENDA (números):\n{options}\n\n"
            "Devuelve DOS listas usando los números del catálogo:\n"
            f'- "own": hasta {COMPLEMENTS_PER_PRODUCT} productos que COMPLEMENTAN a '
            f'"{product_name}" (qué pedirías junto con él), de la que mejor pega a la '
            "que menos.\n"
            f'- "host_of": productos a los que "{product_name}" les serviría como '
            "COMPLEMENTO, SOLO si objetivamente pega, cada uno con su fuerza "
            "(strength 0 a 1). Si no le sirve a ninguno, déjala vacía.\n"
            "Evita sustitutos y duplicados del mismo tipo.\n\n"
            "Responde SOLO con este JSON, sin markdown:\n"
            '{"own": [{"n": <num>, "why": "breve"}], '
            '"host_of": [{"n": <num>, "strength": <0-1>, "why": "breve"}]}'
        )

    # ------------------------------------------------------------------ #
    # Submit + poll + apply
    # ------------------------------------------------------------------ #
    async def _run_batch_and_apply(
        self, db, requests: List[Dict[str, Any]], meta: Dict[str, Dict[str, Any]]
    ) -> int:
        batch = await asyncio.to_thread(
            self.client.messages.batches.create, requests=requests
        )
        print(f"🌙 [complements] batch creado: {batch.id} ({batch.processing_status})")

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

        print(f"🌙 [complements] batch terminado: {current.request_counts}")

        results = await asyncio.to_thread(
            lambda: list(self.client.messages.batches.results(batch.id))
        )

        now = datetime.utcnow()
        coll = db[COMPLEMENTS_COLLECTION]
        own_ops: List[UpdateOne] = []
        # host_id -> {branchId, additions: [{productId, reason, score}]}
        host_additions: Dict[str, Dict[str, Any]] = {}

        for result in results:
            if result.result.type != "succeeded":
                continue
            info = meta.get(result.custom_id)
            if not info:
                continue
            branch_id = info["branchId"]
            candidate_ids = info["candidate_ids"]
            text = "".join(
                b.text for b in result.result.message.content if b.type == "text"
            ).strip()
            own, host_of = self._parse_delta(text)

            # (a) this product's own complements
            own_ops.append(
                UpdateOne(
                    {"_id": result.custom_id},
                    {
                        "$set": {
                            "branchId": branch_id,
                            "complements": self._own_to_complements(own, candidate_ids),
                            "model": SONNET_MODEL,
                            "updatedAt": now,
                        }
                    },
                    upsert=True,
                )
            )

            # (b) this product as a complement of others
            seen_hosts = set()
            for pick in host_of:
                idx = self._idx(pick.get("n"), candidate_ids)
                if idx is None or idx in seen_hosts:
                    continue
                seen_hosts.add(idx)
                host_id = candidate_ids[idx]
                entry = host_additions.setdefault(
                    host_id, {"branchId": branch_id, "additions": []}
                )
                entry["additions"].append(
                    {
                        "productId": result.custom_id,
                        "reason": str(pick.get("why", "")).strip(),
                        "score": self._clamp01(pick.get("strength", 0.5)),
                    }
                )

        if own_ops:
            await coll.bulk_write(own_ops, ordered=False)

        # Apply backward additions: insert each into the host's list, re-sort, cap.
        for host_id, payload in host_additions.items():
            await self._apply_host_additions(
                coll, host_id, payload["branchId"], payload["additions"], now
            )

        return len(own_ops)

    async def _apply_host_additions(
        self, coll, host_id: str, branch_id: str, additions: List[Dict[str, Any]], now
    ) -> None:
        doc = await coll.find_one({"_id": host_id})
        comps = list(doc.get("complements", [])) if doc else []
        adding_ids = {a["productId"] for a in additions}
        # drop any existing entry for the same products (avoid duplicates / refresh)
        comps = [c for c in comps if c.get("productId") not in adding_ids]
        comps.extend(additions)
        comps.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        comps = comps[:COMPLEMENTS_PER_PRODUCT]
        await coll.update_one(
            {"_id": host_id},
            {
                "$set": {
                    "branchId": (doc.get("branchId") if doc else branch_id),
                    "complements": comps,
                    "updatedAt": now,
                }
            },
            upsert=True,
        )

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #
    def _own_to_complements(
        self, own: List[Dict[str, Any]], candidate_ids: List[str]
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for rank, pick in enumerate(own):
            idx = self._idx(pick.get("n"), candidate_ids)
            if idx is None or idx in seen:
                continue
            seen.add(idx)
            out.append(
                {
                    "productId": candidate_ids[idx],
                    "reason": str(pick.get("why", "")).strip(),
                    "score": round(max(0.1, 1.0 - rank * 0.12), 3),
                }
            )
            if len(out) >= COMPLEMENTS_PER_PRODUCT:
                break
        return out

    @staticmethod
    def _idx(n: Any, candidate_ids: List[str]) -> Optional[int]:
        try:
            idx = int(n) - 1
        except (TypeError, ValueError):
            return None
        return idx if 0 <= idx < len(candidate_ids) else None

    @staticmethod
    def _clamp01(value: Any) -> float:
        try:
            return round(min(1.0, max(0.1, float(value))), 3)
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _parse_delta(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            return [], []
        return (data.get("own") or [], data.get("host_of") or [])

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    async def _save_state(
        self,
        db,
        branches: Dict[str, List[Dict[str, Any]]],
        previous_branch_ids: set,
    ) -> None:
        now = datetime.utcnow()
        ops = [
            UpdateOne(
                {"_id": branch_id},
                {
                    "$set": {
                        "productsFp": {
                            p["id"]: self._fingerprint(p["name"]) for p in products
                        },
                        "productCount": len(products),
                        "updatedAt": now,
                    },
                    "$unset": {"productIdsHash": ""},
                },
                upsert=True,
            )
            for branch_id, products in branches.items()
        ]
        if ops:
            await db[STATE_COLLECTION].bulk_write(ops, ordered=False)

        # Drop state for branches that no longer have any product.
        gone = [b for b in previous_branch_ids if b not in branches]
        if gone:
            await db[STATE_COLLECTION].delete_many({"_id": {"$in": gone}})


# Singleton instance
product_complements_indexing_service = ProductComplementsIndexingService()
