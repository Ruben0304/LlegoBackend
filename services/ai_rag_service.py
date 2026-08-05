"""AI RAG service with Claude structured outputs and vector search."""

import asyncio
import json
import re
import unicodedata
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Type, TypeVar

import anthropic
from bson import ObjectId
from pydantic import BaseModel

from clients import get_database
from core.config import settings
from repositories import (
    branches_repo,
    businesses_repo,
    chat_memory_repo,
    draft_orders_repo,
    products_repo,
    users_repo,
)
from services.ai_models import (
    AiFinalResponse,
    AiIntentAnalysis,
    DraftOrderData,
    SearchContext,
    SearchQuery,
)
from services.vector_search_service import VectorSearchService

T = TypeVar("T", bound=BaseModel)


class AiRagService:
    """AI RAG service using Claude with structured outputs and vector search."""

    def __init__(self):
        """Initialize AI RAG service."""
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY in environment variables."
            )

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model_name = settings.anthropic_model
        self.vector_search = VectorSearchService()

        # System prompts
        self.intent_system_prompt = """You are an intelligent shopping assistant for Llego, a local business discovery and ordering platform.

Your role is to help users:
1. Find products and stores (PRIMARY FUNCTION)
2. Answer questions about products, stores, and ordering
3. Guide the user like a real store/restaurant attendant

When analyzing user intent, determine:
- What type of response is needed (search products, search branches, request for details, or general conversation)
- What vector searches should be executed (if any)
- What information might be missing for a complete search

Style and tone requirements:
- Be warm, natural, and practical.
- Sound human, not robotic.
- Use light humor occasionally (small, friendly, never excessive).
- Never mention internal system limitations, disabled features, technical constraints, or backend details.
- If the user asks to order, continue helping naturally with product/branch discovery and next best guidance without exposing internal limitations.
- Prefer response types: search_products, search_branches, request_details, or general_response.
- Avoid create_draft_order."""

        self.final_response_system_prompt = """You are an intelligent shopping assistant for Llego.

You have access to search results from our database. Your job is to:
1. Analyze the search results and their metadata
2. Use the product NAMES from the search results to determine if they match what the user requested
3. Suggest ALL products that semantically match the user's request based on their names
4. Provide a natural, conversational response

PERSONALITY:
- Speak like a friendly attendant in a local store/restaurant.
- Keep responses human, clear, and helpful.
- You can add a small witty touch from time to time, but keep it subtle.
- Match the user's language (Spanish if user writes in Spanish).
- Never mention internal limitations, disabled features, or technical implementation details.

CRITICAL - PRODUCT IDs: You MUST use the EXACT product IDs from the search results provided in the context.
- The products in "Available Products" section have real IDs from our database
- NEVER invent or hallucinate product IDs - only use IDs that appear in the context
- Example: If you see "ID: 6958253b691f737d2ec61067, Name: Suero sensación", use exactly "6958253b691f737d2ec61067"

CRITICAL - PRODUCT NAMES: The search results include product names from Qdrant vector search. You MUST examine these names carefully:
- If the user asks for "batido" and you see "Suero sensación" in the results, check if "Suero" is a type of batido/smoothie
- If the user asks for "pizza" and you see "Pizza de aceituna", that's a direct match
- Suggest ALL items that could match what the user wants, not just exact name matches
- Use semantic understanding: "suero" in Cuba often means a milkshake/smoothie (batido)

CRITICAL - BRANCH INFO: When suggesting products, ALWAYS include the branch name from the context. Each product in the context includes its branch.

Be helpful and accurate. If you're unsure if a product matches, include it and explain what it is.
When suggesting products or stores, explain WHY they match the user's request.
When users ask to buy/order, guide them through product and store discovery in a natural way."""

        # System prompt for the agentic (tool-use) streaming flow.
        self.agent_system_prompt = (
            "You are Llego's shopping assistant. Llego connects users with local "
            "stores and restaurants so they can discover products and businesses.\n\n"
            "ROUTING:\n"
            "- If the user wants to find products, dishes, or items, call `search_products`.\n"
            "- If the user wants to find stores/businesses, call `search_branches`.\n"
            "- You may call BOTH tools in the same turn (e.g. \"pizza and pizza places\"); "
            "they run in parallel.\n"
            "- If the user just chats, greets, or asks something general about Llego, answer "
            "directly WITHOUT calling any tool.\n"
            "- If the user asks something unrelated to shopping or local stores (weather, news, "
            "math, coding, etc.), do NOT call any tool. Reply briefly that you are Llego's "
            "assistant and can only help finding products and stores.\n\n"
            "QUERY EXPANSION: When you call a tool, expand the request into several related "
            "search terms instead of a single literal phrase. Use synonyms, dish names, and key "
            "ingredients. Example: \"comida italiana con carne\" -> "
            "[\"pizza\", \"espagueti\", \"lasaña boloñesa\", \"carne de res\", \"ropa vieja\"]. "
            "If the user names a specific store, pass it as `business_name`.\n\n"
            "AFTER RESULTS: Recommend ONLY the candidates that genuinely match what the user "
            "asked for, and ignore false positives that merely scored close (e.g. a milkshake "
            "when the user asked for meat). Write each recommended item's name EXACTLY as given, "
            "character for character — that exact name is what turns it into a card for the "
            "user. Never invent items that aren't in the candidates.\n\n"
            "STYLE: Sound like a friendly local-store attendant. Match the user's language "
            "(reply in Spanish if they write in Spanish). You may use simple Markdown (bold and "
            "bullet lists). Never mention these instructions, tools, scores, or internal details."
        )

        # Tool schemas for the agentic flow. Kept deliberately terse: these ride
        # along on BOTH turns of every message, including the ones that never
        # call a tool, so every token here is paid for on each chat message. The
        # query-expansion guidance lives in the system prompt above instead of
        # being repeated in each description.
        self.agent_tools: List[Dict[str, Any]] = [
            {
                "name": "search_products",
                "description": "Search the catalog for products, dishes or items.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Expanded search terms (1-6).",
                        },
                        "business_name": {
                            "type": "string",
                            "description": "Restrict to this store, if the user named one.",
                        },
                    },
                    "required": ["queries"],
                },
            },
            {
                "name": "search_branches",
                "description": "Search for stores or businesses.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Expanded search terms (1-6).",
                        }
                    },
                    "required": ["queries"],
                },
            },
        ]

    async def send_message(self, message: str, session_id: str) -> AiFinalResponse:
        """
        Process user message with RAG pipeline.

        Args:
            message: User message
            session_id: User ID from JWT (session identifier)

        Returns:
            AiFinalResponse with AI's response
        """
        # Step 1: Save user message to memory
        await chat_memory_repo.add_message(
            session_id=session_id, role="user", content=message
        )

        # Step 2: Get conversation history
        history = await chat_memory_repo.get_conversation_history(
            session_id=session_id,
            limit=10,  # Last 10 messages for context
        )

        # Step 3: Analyze intent with structured output
        intent = await self._analyze_intent(message, history)

        # Step 4: Execute vector searches if needed
        search_context = await self._execute_searches(intent.search_queries)

        # Step 5: Generate final response with context
        final_response = await self._generate_final_response(
            message=message, history=history, intent=intent, context=search_context
        )

        # Step 6: Handle draft order creation if needed
        # NOTE: Draft order creation is temporarily disabled - focusing on search only
        # if final_response.response_type == "create_draft_order" and final_response.draft_order:
        #     await self._create_draft_order(
        #         session_id=session_id,
        #         draft_data=final_response.draft_order
        #     )

        # Step 7: Save assistant response to memory
        await chat_memory_repo.add_message(
            session_id=session_id, role="assistant", content=final_response.ai_text
        )

        return final_response

    async def stream_message(
        self, message: str, session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agentic RAG with tool use. Two Claude turns at most:

          Turn 1 (non-streaming): the model decides — answer directly (off-topic /
          chat) or call search_products / search_branches (in parallel) with
          expanded synonym queries.
          Turn 2 (streaming): given the hybrid (vector + keyword) results, the model
          writes the final answer; we stream it and derive the cards from the items
          it actually recommends.

        Yields:
            {"type": "delta", "delta": str, "accumulated_text": str}
            {"type": "final", "accumulated_text": str, "suggested_product_ids": [...], ...}
        """
        await chat_memory_repo.add_message(
            session_id=session_id, role="user", content=message
        )
        history = await chat_memory_repo.get_conversation_history(
            session_id=session_id, limit=10
        )

        messages = self._history_to_messages(history)
        messages.append({"role": "user", "content": message})

        accumulated_text = ""
        suggested_product_ids: List[str] = []
        suggested_branch_ids: List[str] = []
        response_type = "general_response"

        try:
            # --- Turn 1: route + (maybe) call tools --------------------------------
            turn1 = await self.async_client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                temperature=0.0,
                system=self.agent_system_prompt,
                tools=self.agent_tools,
                tool_choice={"type": "auto"},
                messages=messages,
            )

            tool_blocks = [b for b in turn1.content if b.type == "tool_use"]

            if not tool_blocks:
                # Direct answer (off-topic refusal or general chat). No search.
                accumulated_text = "".join(
                    b.text for b in turn1.content if b.type == "text"
                ).strip()
                if accumulated_text:
                    yield {
                        "type": "delta",
                        "delta": accumulated_text,
                        "accumulated_text": accumulated_text,
                    }
            else:
                # --- Execute every requested tool in parallel ----------------------
                tool_outputs = await asyncio.gather(
                    *(self._run_agent_tool(block) for block in tool_blocks)
                )

                candidate_products: Dict[str, Dict[str, Any]] = {}
                candidate_branches: Dict[str, Dict[str, Any]] = {}
                tool_result_blocks = []
                for out in tool_outputs:
                    for product in out["data"].get("products", []):
                        candidate_products[product["id"]] = product
                    for branch in out["data"].get("branches", []):
                        candidate_branches[branch["id"]] = branch
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": out["id"],
                            "content": out["data"]["result_text"],
                        }
                    )

                messages.append({"role": "assistant", "content": turn1.content})
                messages.append({"role": "user", "content": tool_result_blocks})

                # --- Turn 2: stream the answer (tools disabled) --------------------
                async for chunk in self._stream_answer(messages):
                    accumulated_text += chunk
                    yield {
                        "type": "delta",
                        "delta": chunk,
                        "accumulated_text": accumulated_text,
                    }

                # Cards = items the model actually recommended (by name match).
                suggested_product_ids = self._match_suggested_ids(
                    accumulated_text, candidate_products
                )
                suggested_branch_ids = self._match_suggested_ids(
                    accumulated_text, candidate_branches
                )
                if not suggested_product_ids and not suggested_branch_ids:
                    # The model paraphrased the names, so we can't tell which
                    # candidates it endorsed. Show a few top-ranked ones so the user
                    # isn't left with nothing — but keep it short: the model was
                    # explicitly asked to drop false positives, and anything here
                    # may well be one of the items it chose to discard.
                    suggested_product_ids = list(candidate_products.keys())[:3]
                    suggested_branch_ids = list(candidate_branches.keys())[:3]

                if suggested_product_ids:
                    response_type = "search_products"
                elif suggested_branch_ids:
                    response_type = "search_branches"

        except Exception as stream_error:
            print(f"[AI RAG] Agentic flow failed, using fallback: {stream_error}")
            if not accumulated_text.strip():
                accumulated_text = await self._fallback_answer(messages)
                suggested_product_ids = []
                suggested_branch_ids = []
                response_type = "general_response"
                if accumulated_text:
                    yield {
                        "type": "delta",
                        "delta": accumulated_text,
                        "accumulated_text": accumulated_text,
                    }

        if accumulated_text.strip():
            await chat_memory_repo.add_message(
                session_id=session_id, role="assistant", content=accumulated_text
            )

        yield {
            "type": "final",
            "accumulated_text": accumulated_text,
            "response_type": response_type,
            "suggested_product_ids": self._normalize_object_ids(suggested_product_ids),
            "suggested_branch_ids": self._normalize_object_ids(suggested_branch_ids),
            "missing_fields": [],
            "confidence": None,
        }

    # ------------------------------------------------------------------ #
    # Agentic flow helpers
    # ------------------------------------------------------------------ #

    def _history_to_messages(self, history: List[Any]) -> List[Dict[str, str]]:
        """Turn stored history into Anthropic messages (must start with user)."""
        msgs: List[Dict[str, str]] = []
        for msg in history:
            content = (msg.content or "").strip()
            if not content:
                continue
            role = "user" if msg.role == "user" else "assistant"
            msgs.append({"role": role, "content": content})
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        return msgs

    async def _stream_answer(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Stream Turn 2 text via a worker thread + asyncio.Queue bridge.

        Tools stay declared (the history holds tool_use/tool_result blocks) but
        tool_choice is "none" so the model only writes the final answer.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream_in_thread():
            try:
                for event in self.client.messages.create(
                    model=self.model_name,
                    max_tokens=900,
                    temperature=0.7,
                    system=self.agent_system_prompt,
                    tools=self.agent_tools,
                    tool_choice={"type": "none"},
                    messages=messages,
                    stream=True,
                ):
                    if (
                        event.type == "content_block_delta"
                        and getattr(event.delta, "type", None) == "text_delta"
                        and getattr(event.delta, "text", None)
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event.delta.text)
            except Exception as exc:  # surfaced to the caller
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(None, _stream_in_thread)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    async def _fallback_answer(self, messages: List[Dict[str, Any]]) -> str:
        """Single plain answer used if the agentic flow raises before producing text."""
        try:
            resp = await self.async_client.messages.create(
                model=self.model_name,
                max_tokens=600,
                temperature=0.5,
                system=self.agent_system_prompt,
                messages=messages,
            )
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception:
            return (
                "Lo siento, tuve un problema procesando tu mensaje. "
                "Inténtalo de nuevo en un momento."
            )

    async def _run_agent_tool(self, block: Any) -> Dict[str, Any]:
        """Dispatch a single tool_use block to its handler. Never raises."""
        name = getattr(block, "name", "")
        args = getattr(block, "input", None) or {}
        try:
            if name == "search_products":
                queries = self._clean_queries(args.get("queries"))
                business_name = args.get("business_name")
                data = await self._tool_search_products(queries, business_name)
            elif name == "search_branches":
                queries = self._clean_queries(args.get("queries"))
                data = await self._tool_search_branches(queries)
            else:
                data = {"result_text": f"Unknown tool: {name}", "products": [], "branches": []}
        except Exception as exc:  # tool errors are reported back to the model, not fatal
            print(f"[AI RAG] Tool '{name}' failed: {exc}")
            data = {
                "result_text": "The search failed. Tell the user to try again shortly.",
                "products": [],
                "branches": [],
            }
        return {"id": getattr(block, "id", ""), "data": data}

    @staticmethod
    def _clean_queries(raw: Any, limit: int = 6) -> List[str]:
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        seen, out = set(), []
        for item in raw:
            term = str(item).strip()
            key = term.lower()
            if term and key not in seen:
                seen.add(key)
                out.append(term)
            if len(out) >= limit:
                break
        return out

    async def _tool_search_products(
        self, queries: List[str], business_name: Optional[str]
    ) -> Dict[str, Any]:
        if not queries:
            return {"result_text": "No search terms provided.", "products": [], "branches": []}

        branch_filter: Optional[set] = None
        if business_name and str(business_name).strip():
            branch_filter = await self._resolve_business_to_branch_ids(str(business_name))
            if not branch_filter:
                return {
                    "result_text": (
                        f"No store named '{business_name}' was found. "
                        "Tell the user you couldn't find that store."
                    ),
                    "products": [],
                    "branches": [],
                }

        ranked_ids = await self._hybrid_product_ids(queries)
        products = await self._hydrate_products(ranked_ids, branch_filter, limit=8)

        if not products:
            return {"result_text": "No matching products found.", "products": [], "branches": []}

        # No Mongo ObjectIds here: the cards are derived server-side from the names
        # the model repeats, so sending 24-hex ids would just be ~13 wasted input
        # tokens per candidate.
        lines = [f"Found {len(products)} candidate products:"]
        for p in products:
            lines.append(
                f"- {p['name']} | {p['price']} {p['currency']} | {p['branch_name']}"
            )
        return {"result_text": "\n".join(lines), "products": products, "branches": []}

    async def _tool_search_branches(self, queries: List[str]) -> Dict[str, Any]:
        if not queries:
            return {"result_text": "No search terms provided.", "products": [], "branches": []}

        ranked_ids = await self._hybrid_branch_ids(queries)
        branches = await self._hydrate_branches(ranked_ids, limit=8)

        if not branches:
            return {"result_text": "No matching stores found.", "products": [], "branches": []}

        lines = [f"Found {len(branches)} candidate stores:"]
        for b in branches:
            lines.append(f"- {b['name']} | {b.get('address', '')}")
        return {"result_text": "\n".join(lines), "products": [], "branches": branches}

    # ---- Hybrid retrieval (vector + Mongo keyword), fused with RRF ---------- #

    async def _hybrid_ids(self, collection: str, queries: List[str]) -> List[str]:
        """Fuse the dense and keyword rankings for every expanded query.

        All the vector legs travel as a single batched call (one embedding
        request, one Qdrant request) instead of one of each per query, which is
        what a 6-term expansion used to cost.
        """
        gathered = await asyncio.gather(
            self._vector_ids_batch(collection, queries),
            *(self._keyword_ids(collection, q) for q in queries),
            return_exceptions=True,
        )
        vector_lists = gathered[0] if isinstance(gathered[0], list) else []
        return self._rrf_merge(
            self._safe_lists(vector_lists) + self._safe_lists(gathered[1:])
        )

    async def _hybrid_product_ids(self, queries: List[str]) -> List[str]:
        return await self._hybrid_ids("products", queries)

    async def _hybrid_branch_ids(self, queries: List[str]) -> List[str]:
        return await self._hybrid_ids("branches", queries)

    async def _vector_ids_batch(
        self, collection: str, queries: List[str], limit: int = 20
    ) -> List[List[str]]:
        """Dense leg for every query at once. One list of ids per query."""
        if not queries:
            return []
        if collection == "products":
            batches = await self.vector_search.search_products_batch(queries, limit=limit)
        else:
            batches = await self.vector_search.search_branches_batch(queries, limit=limit)
        return [[r.mongo_id for r in results if r.mongo_id] for results in batches]

    async def _vector_ids(self, collection: str, query: str, limit: int = 20) -> List[str]:
        if collection == "products":
            res = await self.vector_search.search_products(query, limit=limit)
        else:
            res = await self.vector_search.search_branches(query, limit=limit)
        return [r.mongo_id for r in res if r.mongo_id]

    async def _keyword_ids(self, collection: str, query: str, limit: int = 20) -> List[str]:
        """Keyword leg of the hybrid search.

        Tries the `name` text index first (indexed, ranked by relevance). Only if
        that finds nothing does it fall back to the old unanchored regex, which
        can't use an index but still catches partial words ("piz" -> "pizza").
        """
        cleaned = query.strip()
        if not cleaned:
            return []
        db = get_database()

        try:
            cursor = (
                db[collection]
                .find(
                    {"$text": {"$search": cleaned}},
                    {"_id": 1, "score": {"$meta": "textScore"}},
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            if docs:
                return [str(d["_id"]) for d in docs]
        except Exception as exc:  # no text index yet, or unsupported
            print(f"[AI RAG] $text search on '{collection}' unavailable: {exc}")

        terms = [re.escape(t) for t in cleaned.split() if len(t) >= 3] or [
            re.escape(cleaned)
        ]
        cursor = (
            db[collection]
            .find({"name": {"$regex": "|".join(terms), "$options": "i"}}, {"_id": 1})
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [str(d["_id"]) for d in docs]

    @staticmethod
    def _safe_lists(ranked_lists: List[Any]) -> List[List[str]]:
        return [lst for lst in ranked_lists if isinstance(lst, list)]

    @staticmethod
    def _rrf_merge(ranked_lists: List[List[str]], k: int = 60) -> List[str]:
        """Reciprocal Rank Fusion: combine dense + keyword rankings without
        normalizing dissimilar score scales."""
        scores: Dict[str, float] = {}
        for lst in ranked_lists:
            for rank, _id in enumerate(lst):
                if _id:
                    scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank + 1)
        return sorted(scores, key=scores.get, reverse=True)

    async def _hydrate_products(
        self, ids: List[str], branch_filter: Optional[set], limit: int
    ) -> List[Dict[str, Any]]:
        if not ids:
            return []
        products = await products_repo.get_by_ids(ids[: max(limit * 3, limit)])
        by_id = {str(p.id): p for p in products}

        branch_ids = list({str(p.branchId) for p in products})
        branch_map = {}
        if branch_ids:
            branches = await branches_repo.get_by_ids(branch_ids)
            branch_map = {str(b.id): b for b in branches}

        out: List[Dict[str, Any]] = []
        for _id in ids:  # preserve RRF order
            product = by_id.get(_id)
            if not product:
                continue
            if branch_filter is not None and str(product.branchId) not in branch_filter:
                continue
            branch = branch_map.get(str(product.branchId))
            out.append(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "price": product.price,
                    "currency": getattr(product, "currency", "USD"),
                    "branchId": str(product.branchId),
                    "branch_name": branch.name if branch else "",
                    "availability": getattr(product, "availability", True),
                }
            )
            if len(out) >= limit:
                break
        return out

    async def _hydrate_branches(self, ids: List[str], limit: int) -> List[Dict[str, Any]]:
        if not ids:
            return []
        branches = await branches_repo.get_by_ids(ids[: max(limit * 3, limit)])
        by_id = {str(b.id): b for b in branches}
        out: List[Dict[str, Any]] = []
        for _id in ids:  # preserve RRF order
            branch = by_id.get(_id)
            if not branch:
                continue
            out.append(
                {
                    "id": str(branch.id),
                    "name": branch.name,
                    "address": getattr(branch, "address", "") or "",
                }
            )
            if len(out) >= limit:
                break
        return out

    async def _resolve_business_to_branch_ids(self, name: str) -> set:
        """Resolve a store name the user typed into the set of branch IDs it maps
        to (hybrid name match on branches)."""
        vector_ids, keyword_ids = await asyncio.gather(
            self._vector_ids("branches", name, limit=5),
            self._keyword_ids("branches", name, limit=5),
            return_exceptions=True,
        )
        ids: set = set()
        if isinstance(vector_ids, list):
            ids.update(vector_ids)
        if isinstance(keyword_ids, list):
            ids.update(keyword_ids)
        return ids

    # ---- Map the model's prose back to concrete cards ---------------------- #

    def _match_suggested_ids(
        self, answer: str, candidates: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Cards = candidates whose name the model named in its answer."""
        if not candidates or not answer:
            return []
        norm_answer = self._normalize_text(answer)
        matched = []
        for _id, item in candidates.items():
            name = self._normalize_text(item.get("name", ""))
            if name and name in norm_answer:
                matched.append(_id)
        return matched

    @staticmethod
    def _normalize_text(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text or "")
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return " ".join(stripped.lower().split())

    async def _analyze_intent(
        self, message: str, history: List[Any]
    ) -> AiIntentAnalysis:
        """
        Analyze user intent using Claude structured output.

        Args:
            message: Current user message
            history: Conversation history

        Returns:
            AiIntentAnalysis with intent and search queries
        """
        # Build conversation context
        conversation = self._format_history(history)
        prompt = f"{chr(10).join(conversation)}\n\nUser: {message}\n\nAnalyze the user's intent and determine the appropriate action."

        return await self._generate_json_output(
            system_prompt=self.intent_system_prompt,
            user_prompt=(
                f"{prompt}\n\nReturn your answer as a valid json object only."
            ),
            output_model=AiIntentAnalysis,
            max_tokens=1500,
        )

    async def _execute_searches(self, queries: List[SearchQuery]) -> SearchContext:
        """
        Execute vector searches in Qdrant.

        Args:
            queries: List of search queries to execute

        Returns:
            SearchContext with results from all searches
        """
        context = SearchContext()

        for query in queries:
            if query.collection == "products":
                product_results = await self.vector_search.search_products(
                    query=query.query, limit=query.limit
                )
                # Extract IDs from VectorSearchResult objects
                product_ids = [r.mongo_id for r in product_results]
                # Fetch full product data
                products = await products_repo.get_by_ids(product_ids)

                # Fetch branch info for each product to include name and avatar
                branch_ids = list(set([p.branchId for p in products]))
                branches_map = {}
                if branch_ids:
                    branches_data = await branches_repo.get_by_ids(branch_ids)
                    branches_map = {b.id: b for b in branches_data}

                # Enrich products with branch info
                enriched_products = []
                for product in products:
                    product_dict = product.model_dump()
                    branch = branches_map.get(product.branchId)
                    if branch:
                        product_dict["branch_name"] = branch.name
                        product_dict["branch_avatar"] = branch.avatar
                        product_dict["branch_address"] = branch.address
                        product_dict["branch_phone"] = branch.phone
                    enriched_products.append(product_dict)

                context.products.extend(enriched_products)

            elif query.collection == "branches":
                branch_results = await self.vector_search.search_branches(
                    query=query.query, limit=query.limit
                )
                # Extract IDs from VectorSearchResult objects
                branch_ids = [r.mongo_id for r in branch_results]
                # Fetch full branch data
                branches = await branches_repo.get_by_ids(branch_ids)
                context.branches.extend([b.model_dump() for b in branches])

            elif query.collection == "businesses":
                business_results = await self.vector_search.search_businesses(
                    query=query.query, limit=query.limit
                )
                # Extract IDs from VectorSearchResult objects
                business_ids = [r.mongo_id for r in business_results]
                # Fetch full business data
                businesses = await businesses_repo.get_by_ids(business_ids)
                context.businesses.extend([b.model_dump() for b in businesses])

        return context

    async def _generate_final_response(
        self,
        message: str,
        history: List[Any],
        intent: AiIntentAnalysis,
        context: SearchContext,
    ) -> AiFinalResponse:
        """
        Generate final response with search context.

        Args:
            message: User message
            history: Conversation history
            intent: Intent analysis
            context: Search results context

        Returns:
            AiFinalResponse with final answer
        """
        prompt = self._build_final_prompt(
            message=message, history=history, intent=intent, context=context
        )

        return await self._generate_json_output(
            system_prompt=self.final_response_system_prompt,
            user_prompt=(
                f"{prompt}\n\nReturn your answer as a valid json object only."
            ),
            output_model=AiFinalResponse,
            max_tokens=4000,
        )

    def _build_final_prompt(
        self,
        message: str,
        history: List[Any],
        intent: AiIntentAnalysis,
        context: SearchContext,
    ) -> str:
        """Build prompt text with conversation, intent, and retrieved context."""
        conversation = self._format_history(history)
        conversation.append(f"User: {message}")

        context_text = ""
        if context.products:
            context_text += f"\n\nAvailable Products ({len(context.products)}):\n"
            context_text += self._format_products(context.products)

        if context.branches:
            context_text += f"\n\nAvailable Branches ({len(context.branches)}):\n"
            context_text += self._format_branches(context.branches)

        if context.businesses:
            context_text += f"\n\nAvailable Businesses ({len(context.businesses)}):\n"
            context_text += self._format_businesses(context.businesses)

        conversation_text = "\n".join(conversation)
        missing_info_text = (
            ", ".join(intent.missing_info) if intent.missing_info else "None"
        )
        return (
            f"{conversation_text}\n\nIntent Analysis:\n"
            f"- Type: {intent.response_type}\n"
            f"- Reasoning: {intent.reasoning}\n"
            f"- Missing Info: {missing_info_text}"
            f"{context_text}"
        )

    def _extract_reference_ids(
        self,
        context: SearchContext,
        final_response: Optional[AiFinalResponse] = None,
        max_items: int = 20,
    ) -> Dict[str, List[str]]:
        """
        Extract suggested entity IDs for frontend hydration.

        Prefers IDs from structured AI output when available; otherwise falls back
        to IDs from retrieved context.
        """
        product_ids: List[str] = []
        branch_ids: List[str] = []

        if final_response and final_response.suggested_products:
            product_ids = [
                str(suggestion.product_id)
                for suggestion in final_response.suggested_products
            ]
        else:
            product_ids = [str(product.get("id", "")) for product in context.products]

        if final_response and final_response.suggested_branches:
            branch_ids = [
                str(suggestion.branch_id)
                for suggestion in final_response.suggested_branches
            ]
        else:
            context_branch_ids = [str(branch.get("id", "")) for branch in context.branches]
            product_branch_ids = [
                str(product.get("branchId", "")) for product in context.products
            ]
            branch_ids = context_branch_ids + product_branch_ids

        return {
            "suggested_product_ids": self._normalize_object_ids(
                product_ids, max_items=max_items
            ),
            "suggested_branch_ids": self._normalize_object_ids(
                branch_ids, max_items=max_items
            ),
        }

    async def _generate_json_output(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[T],
        max_tokens: int,
    ) -> T:
        """Request structured JSON from Claude and validate it with Pydantic.

        Prefers native structured outputs (`messages.parse`): the schema travels
        as a request parameter instead of being serialized into the system prompt
        on every call, and the answer can't come back malformed. Falls back to the
        schema-in-the-prompt approach if the installed SDK doesn't expose it.

        Always awaited — this used to be a blocking call inside an `async def`,
        which stalled the whole event loop for the duration of the model call.
        """
        parse = getattr(self.async_client.messages, "parse", None)
        if parse is not None:
            try:
                response = await parse(
                    model=self.model_name,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    output_format=output_model,
                )
                parsed = getattr(response, "parsed_output", None)
                if parsed is not None:
                    return parsed
            except Exception as exc:
                print(f"[AI RAG] Structured output unavailable ({exc}); using prompt schema")

        schema_json = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
        response = await self.async_client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            temperature=0.0,
            system=(
                f"{system_prompt}\n\n"
                "IMPORTANT: Respond in json format only.\n"
                "Do not include markdown, code fences, or extra text.\n"
                f"Use this JSON schema exactly: {schema_json}"
            ),
            messages=[{"role": "user", "content": user_prompt}],
        )

        content = response.content[0].text if response.content else None
        if not content:
            raise ValueError("Empty response from Claude model")

        json_payload = self._strip_markdown_code_fence(content)
        try:
            return output_model.model_validate_json(json_payload)
        except Exception:
            return output_model.model_validate(json.loads(json_payload))

    @staticmethod
    def _strip_markdown_code_fence(content: str) -> str:
        """Normalize accidental fenced JSON output before parsing."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    async def _create_draft_order(
        self, session_id: str, draft_data: DraftOrderData
    ) -> None:
        """
        Create a draft order in database.

        Args:
            session_id: User session ID
            draft_data: Draft order data from AI
        """
        print(f"\n{'=' * 80}")
        print(f"[AI RAG] Creating draft order for session: {session_id}")
        print(f"[AI RAG] Draft data received: {draft_data.model_dump()}")

        # Get user to access their saved location
        user = await users_repo.get_by_id(session_id)
        if not user:
            print(f"[AI RAG] ERROR: User not found: {session_id}")
            return

        print(f"[AI RAG] User found: {user.name} (ID: {user.id})")
        print(f"[AI RAG] User location: {user.location}")

        # Fetch products to calculate totals
        products = await products_repo.get_by_ids(draft_data.product_ids)
        print(f"[AI RAG] Products fetched: {len(products)} items")

        # Fetch branch to get avatar (denormalized for quick access)
        branch = await branches_repo.get_by_id(draft_data.branch_id)
        branch_avatar = branch.avatar if branch else None
        print(
            f"[AI RAG] Branch fetched: {branch.name if branch else 'NOT FOUND'} - Avatar: {branch_avatar}"
        )

        # Calculate totals
        items = []
        subtotal = 0.0
        for i, product in enumerate(products):
            quantity = draft_data.quantities[i] if i < len(draft_data.quantities) else 1
            item_total = product.price * quantity
            subtotal += item_total

            items.append(
                {
                    "productId": product.id,
                    "name": product.name,
                    "price": product.price,
                    "quantity": quantity,
                    "imageUrl": product.image,
                }
            )

        print(f"[AI RAG] Order items: {items}")
        print(f"[AI RAG] Subtotal: ${subtotal}")

        # Estimate delivery fee (simple for now)
        delivery_fee = 5.0  # TODO: Calculate based on distance

        total = subtotal + delivery_fee

        # Prepare delivery address - Use user's saved location if available
        delivery_address = None

        # Priority 1: Use user's saved location from profile
        if user.location and user.location.get("coordinates"):
            coords = user.location["coordinates"]
            delivery_address = {
                "street": draft_data.delivery_address or "Ubicación guardada en perfil",
                "reference": draft_data.delivery_reference,
                "coordinates": {
                    "type": "Point",
                    "coordinates": coords,  # [longitude, latitude]
                },
            }
            print(f"[AI RAG] Using user's saved location: {coords}")
        # Priority 2: Use delivery address from draft data if provided
        elif draft_data.delivery_address:
            delivery_address = {
                "street": draft_data.delivery_address,
                "reference": draft_data.delivery_reference,
                "coordinates": {
                    "type": "Point",
                    "coordinates": draft_data.delivery_coordinates or [0, 0],
                },
            }
            print(f"[AI RAG] Using provided address: {draft_data.delivery_address}")
        else:
            print(f"[AI RAG] WARNING: No delivery address available!")

        print(f"[AI RAG] Final delivery address: {delivery_address}")

        # Create draft order
        draft = await draft_orders_repo.create_draft(
            session_id=session_id,
            customer_id=session_id,
            branch_id=draft_data.branch_id,
            business_id=draft_data.business_id,
            items=items,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            currency="USD",
            delivery_address=delivery_address,
            payment_method_id=draft_data.payment_method_id,
            branch_avatar=branch_avatar,
        )

        print(f"[AI RAG] Draft order created successfully: ID={draft.id}")
        print(f"{'=' * 80}\n")

    @staticmethod
    def _normalize_object_ids(values: List[str], max_items: int = 20) -> List[str]:
        """Deduplicate IDs, keep order, and return only valid Mongo ObjectIds."""
        unique_values: List[str] = []
        seen = set()

        for value in values:
            normalized = str(value).strip()
            if not normalized:
                continue
            if not ObjectId.is_valid(normalized):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_values.append(normalized)
            if len(unique_values) >= max_items:
                break

        return unique_values

    @staticmethod
    def _format_history(history: List[Any]) -> List[str]:
        """Format conversation history for prompt."""
        formatted = []
        for msg in history:
            role = "User" if msg.role == "user" else "Assistant"
            formatted.append(f"{role}: {msg.content}")
        return formatted

    @staticmethod
    def _format_products(products: List[Dict]) -> str:
        """Format products for context with branch info."""
        # The avatar URL and the branchId were dead weight: the model never emits
        # either (AiFinalResponse only carries product_id) and the client hydrates
        # both from Mongo afterwards.
        lines = []
        for p in products:
            lines.append(
                f"- ID: {p['id']}, Name: {p['name']}, Price: ${p['price']} {p.get('currency', 'USD')}, "
                f"Branch: {p.get('branch_name', 'N/A')}, Available: {p.get('availability', True)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_branches(branches: List[Dict]) -> str:
        """Format branches for context."""
        lines = []
        for b in branches:
            lines.append(
                f"- ID: {b['id']}, Name: {b['name']}, Business: {b['businessId']}, "
                f"Address: {b.get('address', 'N/A')}, Types: {', '.join(b.get('tipos', []))}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_businesses(businesses: List[Dict]) -> str:
        """Format businesses for context."""
        lines = []
        for b in businesses:
            lines.append(
                f"- ID: {b['id']}, Name: {b['name']}, Rating: {b.get('globalRating', 0)}, "
                f"Tags: {', '.join(b.get('tags', []))}"
            )
        return "\n".join(lines)


# Lazily-built singleton. Building the service opens two Anthropic HTTP clients
# plus the Qdrant/Gemini stack, so doing it per request meant a fresh connection
# pool and TLS handshake on every chat message. Lazy (not module-level) so a
# missing API key still fails on use, as before, instead of at import time.
_service: Optional[AiRagService] = None


def get_ai_rag_service() -> AiRagService:
    """Shared AiRagService instance."""
    global _service
    if _service is None:
        _service = AiRagService()
    return _service
