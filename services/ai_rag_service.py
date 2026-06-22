"""AI RAG service with Claude structured outputs and vector search."""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypeVar

import anthropic
from bson import ObjectId
from pydantic import BaseModel

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

CRITICAL - BRANCH INFO: When suggesting products, ALWAYS include the branch name and branch avatar information from the context. Each product in the context includes its branch details.

Be helpful and accurate. If you're unsure if a product matches, include it and explain what it is.
When suggesting products or stores, explain WHY they match the user's request.
When users ask to buy/order, guide them through product and store discovery in a natural way."""

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
        Stream AI response tokens in real-time and return reference IDs at the end.

        Yields events:
            {"type": "delta", "delta": str, "accumulated_text": str}
            {"type": "final", "accumulated_text": str, "suggested_product_ids": [...], ...}
        """
        # Step 1: Save user message to memory
        await chat_memory_repo.add_message(
            session_id=session_id, role="user", content=message
        )

        # Step 2: Get conversation history
        history = await chat_memory_repo.get_conversation_history(
            session_id=session_id,
            limit=10,
        )

        # Step 3: Analyze intent and fetch search context
        intent = await self._analyze_intent(message, history)
        search_context = await self._execute_searches(intent.search_queries)

        # Step 4: Build streaming prompt (plain text response)
        prompt = self._build_final_prompt(
            message=message, history=history, intent=intent, context=search_context
        )

        accumulated_text = ""
        fallback_response: Optional[AiFinalResponse] = None

        try:
            stream = await self.async_client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                system=(
                    f"{self.final_response_system_prompt}\n\n"
                    "IMPORTANT: Respond with plain natural text only for the end user.\n"
                    "Do not return JSON, markdown, code fences, or internal notes."
                ),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                stream=True,
            )
            async for event in stream:
                if (
                    event.type == "content_block_delta"
                    and hasattr(event.delta, "text")
                ):
                    text_delta = event.delta.text
                    if not text_delta:
                        continue
                    accumulated_text += text_delta
                    yield {
                        "type": "delta",
                        "delta": text_delta,
                        "accumulated_text": accumulated_text,
                    }

        except Exception as stream_error:
            print(f"[AI RAG] Streaming failed, using fallback response: {stream_error}")
            if not accumulated_text.strip():
                fallback_response = await self._generate_final_response(
                    message=message,
                    history=history,
                    intent=intent,
                    context=search_context,
                )
                accumulated_text = fallback_response.ai_text
                if accumulated_text:
                    yield {
                        "type": "delta",
                        "delta": accumulated_text,
                        "accumulated_text": accumulated_text,
                    }

        # Step 5: Save assistant text to memory
        if accumulated_text.strip():
            await chat_memory_repo.add_message(
                session_id=session_id, role="assistant", content=accumulated_text
            )

        # Step 6: Send final metadata with reference IDs
        references = self._extract_reference_ids(
            context=search_context, final_response=fallback_response
        )
        if intent.response_type == "search_branches":
            references["suggested_product_ids"] = []
        elif intent.response_type == "search_products":
            pass
        else:
            # For general chat/details, only send references when they actually exist.
            if not search_context.products:
                references["suggested_product_ids"] = []
            if not search_context.branches:
                references["suggested_branch_ids"] = []

        yield {
            "type": "final",
            "accumulated_text": accumulated_text,
            "suggested_product_ids": references["suggested_product_ids"],
            "suggested_branch_ids": references["suggested_branch_ids"],
            "missing_fields": (
                fallback_response.missing_fields
                if fallback_response
                else intent.missing_info
            ),
            "confidence": (
                fallback_response.confidence if fallback_response else intent.confidence
            ),
        }

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

        return self._generate_json_output(
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

        return self._generate_json_output(
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

    def _generate_json_output(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[T],
        max_tokens: int,
    ) -> T:
        """Request structured JSON from Claude and validate it with Pydantic."""
        schema_json = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            temperature=1.0,
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
        lines = []
        for p in products:
            branch_info = f"Branch: {p.get('branch_name', 'N/A')}"
            if p.get("branch_avatar"):
                branch_info += f" (Avatar: {p['branch_avatar']})"
            lines.append(
                f"- ID: {p['id']}, Name: {p['name']}, Price: ${p['price']} {p.get('currency', 'USD')}, "
                f"{branch_info}, BranchID: {p['branchId']}, Available: {p.get('availability', True)}"
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
