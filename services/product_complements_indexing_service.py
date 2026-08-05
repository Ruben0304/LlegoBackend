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

Model: Haiku 4.5, without extended thinking (Haiku only thinks if you pass a
`thinking` block, and we never do). On top of that: Batch API (50% cheaper,
offline) and structured outputs, so a malformed answer can't burn a request.

Nothing reaches the model unless the delta says so — a night with no product
added, renamed or deleted issues zero requests. And a product is only marked as
done once its answer actually landed in Mongo, so a failed request is retried
the next night instead of being silently written off.
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

# Haiku is enough here: the task is picking numbers off a short menu, not
# reasoning. No `thinking` block is ever sent — that keeps output tokens to the
# JSON alone.
MODEL = "claude-haiku-4-5"

COMPLEMENTS_COLLECTION = "product_complements"
STATE_COLLECTION = "recommendation_index_state"

MAX_MENU = 120  # cap catalog names per prompt (huge catalogs)
COMPLEMENTS_PER_PRODUCT = 8  # max complements stored per product
MAX_WHY_WORDS = 4  # keep the stored reason (and the output bill) short
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

# Forces the model's answer into this exact shape. Without it a Haiku reply that
# drifts (markdown fence, extra prose, a missing field) is a request paid for and
# thrown away.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "own": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["n", "why"],
                "additionalProperties": False,
            },
        },
        "host_of": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "strength": {"type": "number"},
                    "why": {"type": "string"},
                },
                "required": ["n", "strength", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["own", "host_of"],
    "additionalProperties": False,
}


class ProductComplementsIndexingService:
    """Incremental per-product complements indexing with Haiku (Batch API)."""

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
        indexed_ids = await self._load_indexed_ids(db)

        # `settled` = productId -> fingerprint for everything that needs no work
        # this run. Only what ends up in here gets its fingerprint persisted.
        removed, targets, changed_by_branch, settled = self._diff(
            branches, state, indexed_ids
        )
        fp_by_id = {
            p["id"]: self._fingerprint(p["name"])
            for products in branches.values()
            for p in products
        }

        deleted = sum(len(v) for v in removed.values())
        if not removed and not targets:
            print("🌙 [complements] sin cambios — no se llama al modelo")
            return {"deleted": 0, "indexed": 0, "skipped": "no_changes"}

        print(
            f"🌙 [complements] borrados={deleted} | "
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
            # A target with no usable catalog (branch has a single product) can
            # never produce a request — settle it so it stops being re-evaluated
            # every single night.
            for _, product_id in targets:
                if product_id not in meta:
                    settled[product_id] = fp_by_id[product_id]
            if requests:
                print(f"🌙 [complements] batch con {len(requests)} productos...")
                succeeded = await self._run_batch_and_apply(db, requests, meta)
                indexed = len(succeeded)
                for product_id in succeeded:
                    settled[product_id] = fp_by_id[product_id]

        # 4) Persist fingerprints — only for products that are really indexed.
        await self._save_state(db, branches, state, settled)

        pending = sum(1 for _, pid in targets if pid not in settled)
        return {"deleted": deleted, "indexed": indexed, "pending": pending}

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
            name = (d.get("name") or "").strip()
            if not name:
                continue  # nameless: can't be indexed, and useless as a candidate
            branches.setdefault(branch_id, []).append(
                {"id": str(d["_id"]), "name": name}
            )
        return branches

    async def _load_indexed_ids(self, db) -> set:
        """Products that already have a complements doc.

        Lets the diff tell "unchanged and indexed" (skip) apart from "unchanged
        but never indexed" (a previous run failed — retry it).
        """
        docs = await db[COMPLEMENTS_COLLECTION].find({}, {"_id": 1}).to_list(
            length=None
        )
        return {d["_id"] for d in docs}

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

    def _diff(
        self,
        branches: Dict[str, List[Dict[str, Any]]],
        state: Dict[str, Dict[str, Any]],
        indexed_ids: set,
    ) -> Tuple[
        Dict[str, List[str]],
        List[Tuple[str, str]],
        Dict[str, List[str]],
        Dict[str, str],
    ]:
        """Split every product into: delete it, re-index it, or leave it alone.

        A product only becomes a target (i.e. only costs tokens) when its name
        changed, it's brand new, or it has no complements doc yet. Everything
        else lands in `settled` and is never sent to the model.
        """
        removed: Dict[str, List[str]] = {}
        targets: List[Tuple[str, str]] = []  # (branchId, productId) added or changed
        changed_by_branch: Dict[str, List[str]] = {}
        settled: Dict[str, str] = {}  # productId -> fingerprint, nothing to do

        for branch_id in set(branches) | set(state):
            products = branches.get(branch_id, [])
            cur_fp = {p["id"]: self._fingerprint(p["name"]) for p in products}
            prev_fp: Dict[str, str] = (state.get(branch_id) or {}).get("fp") or {}
            # A lone product has no siblings to complement it, so it never gets a
            # doc — don't let its absence keep re-triggering forever.
            indexable = len(products) >= 2

            rem = [pid for pid in prev_fp if pid not in cur_fp]
            if rem:
                removed[branch_id] = rem

            for pid, fp in cur_fp.items():
                known = prev_fp.get(pid)
                if known is None and not prev_fp and pid in indexed_ids:
                    # No per-product state for this branch (legacy hash-only
                    # format, or state lost) but the product already has
                    # complements: assume it's current instead of paying to
                    # reindex the whole branch, like the old code did.
                    known = fp
                if known == fp and (pid in indexed_ids or not indexable):
                    settled[pid] = fp
                    continue
                targets.append((branch_id, pid))
                if known is not None:
                    # Existed before: drop its stale entries from siblings first.
                    changed_by_branch.setdefault(branch_id, []).append(pid)

        return removed, targets, changed_by_branch, settled

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
                        "model": MODEL,
                        # Cap, not a budget: only what's generated is billed, and
                        # the prompt keeps the answer to a few short lines.
                        "max_tokens": 700,
                        "system": _SYSTEM_PROMPT,
                        "output_config": {
                            "format": {
                                "type": "json_schema",
                                "schema": _RESPONSE_SCHEMA,
                            }
                        },
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
            f'- "host_of": hasta {COMPLEMENTS_PER_PRODUCT} productos a los que '
            f'"{product_name}" les serviría como COMPLEMENTO, SOLO si '
            "objetivamente pega, cada uno con su fuerza (strength 0 a 1). Si no "
            "le sirve a ninguno, déjala vacía.\n"
            "Evita sustitutos y duplicados del mismo tipo.\n"
            f'Cada "why" es de máximo {MAX_WHY_WORDS} palabras.\n\n'
            "Responde SOLO con este JSON, sin markdown:\n"
            '{"own": [{"n": <num>, "why": "breve"}], '
            '"host_of": [{"n": <num>, "strength": <0-1>, "why": "breve"}]}'
        )

    # ------------------------------------------------------------------ #
    # Submit + poll + apply
    # ------------------------------------------------------------------ #
    async def _create_batch(self, requests: List[Dict[str, Any]]):
        """Submit the batch, falling back to plain JSON if the API rejects the
        structured-output field (older SDK/endpoint). Creation is free, so the
        retry costs nothing."""
        try:
            return await asyncio.to_thread(
                self.client.messages.batches.create, requests=requests
            )
        except anthropic.BadRequestError as exc:
            if "output_config" not in str(exc):
                raise
            print(f"⚠ [complements] output_config rechazado ({exc}); sin schema")
            plain = [
                {**r, "params": {k: v for k, v in r["params"].items()
                                 if k != "output_config"}}
                for r in requests
            ]
            return await asyncio.to_thread(
                self.client.messages.batches.create, requests=plain
            )

    async def _run_batch_and_apply(
        self, db, requests: List[Dict[str, Any]], meta: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Returns the ids whose complements actually made it into Mongo."""
        batch = await self._create_batch(requests)
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
        succeeded_ids: List[str] = []
        unusable = 0
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
            parsed = self._parse_delta(text)
            if parsed is None:
                # Unreadable answer: leave the product unsettled so the next run
                # retries it, instead of storing an empty list as if it were the
                # real result.
                unusable += 1
                continue
            own, host_of = parsed

            # (a) this product's own complements
            succeeded_ids.append(result.custom_id)
            own_ops.append(
                UpdateOne(
                    {"_id": result.custom_id},
                    {
                        "$set": {
                            "branchId": branch_id,
                            "complements": self._own_to_complements(own, candidate_ids),
                            "model": MODEL,
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

        if unusable:
            print(f"⚠ [complements] {unusable} respuestas ilegibles — se reintentan")
        return succeeded_ids

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
    def _parse_delta(
        text: str,
    ) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
        """None means "couldn't read it" — distinct from a valid empty answer."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return (data.get("own") or [], data.get("host_of") or [])

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    async def _save_state(
        self,
        db,
        branches: Dict[str, List[Dict[str, Any]]],
        state: Dict[str, Dict[str, Any]],
        settled: Dict[str, str],
    ) -> None:
        """Persist fingerprints for settled products only.

        A product whose request failed keeps its old (or missing) fingerprint, so
        the next run picks it up again instead of writing it off as done. Nothing
        is written for branches whose map didn't move.
        """
        now = datetime.utcnow()
        ops: List[UpdateOne] = []
        for branch_id, products in branches.items():
            st = state.get(branch_id)
            prev: Dict[str, str] = (st or {}).get("fp") or {}
            current_ids = {p["id"] for p in products}
            fp = {pid: f for pid, f in prev.items() if pid in current_ids}
            for p in products:
                done = settled.get(p["id"])
                if done is not None:
                    fp[p["id"]] = done
            if st is not None and st.get("hash") is None and fp == prev:
                continue  # nothing moved in this branch
            ops.append(
                UpdateOne(
                    {"_id": branch_id},
                    {
                        "$set": {
                            "productsFp": fp,
                            "productCount": len(products),
                            "updatedAt": now,
                        },
                        "$unset": {"productIdsHash": ""},
                    },
                    upsert=True,
                )
            )
        if ops:
            await db[STATE_COLLECTION].bulk_write(ops, ordered=False)

        # Drop state for branches that no longer have any product.
        gone = [b for b in state if b not in branches]
        if gone:
            await db[STATE_COLLECTION].delete_many({"_id": {"$in": gone}})


# Singleton instance
product_complements_indexing_service = ProductComplementsIndexingService()
