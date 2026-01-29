"""AI RAG service with Gemini structured outputs and vector search."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from google import genai
from google.genai import types

from clients import get_gemini_client
from core.config import settings
from repositories import (
    chat_memory_repo,
    draft_orders_repo,
    products_repo,
    branches_repo,
    businesses_repo,
    payment_methods_repo,
    users_repo
)
from services.vector_search_service import VectorSearchService, VectorSearchResult
from services.ai_models import (
    AiIntentAnalysis,
    AiFinalResponse,
    SearchQuery,
    SearchContext,
    DraftOrderData
)


class AiRagService:
    """AI RAG service using Gemini with structured outputs and Qdrant vector search."""

    def __init__(self):
        """Initialize AI RAG service."""
        self.client = get_gemini_client()
        self.model_name = settings.gemini_model
        self.vector_search = VectorSearchService()

        # System prompts
        self.intent_system_prompt = """You are an intelligent shopping assistant for Llego, a local business discovery and ordering platform.

Your role is to help users:
1. Find products and stores
2. Create orders with all necessary details
3. Answer questions about products, stores, and ordering

When analyzing user intent, determine:
- What type of response is needed (search, order creation, request for details, or general conversation)
- What vector searches should be executed (if any)
- What information is missing (payment method, etc.)

IMPORTANT: Users have a saved location in their profile. When creating orders, the system will automatically use their saved location for delivery. DO NOT ask for delivery address unless explicitly needed.

Be conversational and helpful. If the user is vague, ask clarifying questions.
If creating an order, ensure all required info is present: products and payment method. The delivery location will be taken from their profile automatically.
All products in an order MUST be from the same branch/store."""

        self.final_response_system_prompt = """You are an intelligent shopping assistant for Llego.

You have access to search results from our database. Your job is to:
1. Analyze the search results and their metadata
2. Use the product NAMES from the search results to determine if they match what the user requested
3. Suggest ALL products that semantically match the user's request based on their names
4. If creating an order, validate that all products are from the same branch
5. Provide a natural, conversational response

CRITICAL: The search results include product names from Qdrant vector search. You MUST examine these names carefully:
- If the user asks for "batido" and you see "Suero sensación" in the results, check if "Suero" is a type of batido/smoothie
- If the user asks for "pizza" and you see "Pizza de aceituna", that's a direct match
- Suggest ALL items that could match what the user wants, not just exact name matches
- Use semantic understanding: "suero" in Cuba often means a milkshake/smoothie (batido)

Be helpful and accurate. If you're unsure if a product matches, include it and explain what it is.
When suggesting products or stores, explain WHY they match the user's request.

IMPORTANT: For draft orders, ALL products must be from the same branch. If user selects products from different branches, you must create separate orders or ask them to choose one branch."""

    async def send_message(
        self,
        message: str,
        session_id: str
    ) -> AiFinalResponse:
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
            session_id=session_id,
            role="user",
            content=message
        )

        # Step 2: Get conversation history
        history = await chat_memory_repo.get_conversation_history(
            session_id=session_id,
            limit=10  # Last 10 messages for context
        )

        # Step 3: Analyze intent with Gemini structured output
        intent = await self._analyze_intent(message, history)

        # Step 4: Execute vector searches if needed
        search_context = await self._execute_searches(intent.search_queries)

        # Step 5: Generate final response with context
        final_response = await self._generate_final_response(
            message=message,
            history=history,
            intent=intent,
            context=search_context
        )

        # Step 6: Handle draft order creation if needed
        if final_response.response_type == "create_draft_order" and final_response.draft_order:
            await self._create_draft_order(
                session_id=session_id,
                draft_data=final_response.draft_order
            )

        # Step 7: Save assistant response to memory
        await chat_memory_repo.add_message(
            session_id=session_id,
            role="assistant",
            content=final_response.ai_text
        )

        return final_response

    async def _analyze_intent(
        self,
        message: str,
        history: List[Any]
    ) -> AiIntentAnalysis:
        """
        Analyze user intent using Gemini structured output.

        Args:
            message: Current user message
            history: Conversation history

        Returns:
            AiIntentAnalysis with intent and search queries
        """
        # Build conversation context
        conversation = self._format_history(history)
        prompt = f"{chr(10).join(conversation)}\n\nUser: {message}\n\nAnalyze the user's intent and determine the appropriate action."

        # Generate with structured output (following Gemini SDK guidelines)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.intent_system_prompt,
                response_mime_type="application/json",
                response_schema=AiIntentAnalysis
            )
        )

        # Parse response (response.text is already JSON string)
        import json
        if not response.text:
            raise ValueError("Empty response from AI model")
        return AiIntentAnalysis(**json.loads(response.text))

    async def _execute_searches(
        self,
        queries: List[SearchQuery]
    ) -> SearchContext:
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
                    query=query.query,
                    limit=query.limit
                )
                # Extract IDs from VectorSearchResult objects
                product_ids = [r.mongo_id for r in product_results]
                # Fetch full product data
                products = await products_repo.get_by_ids(product_ids)
                context.products.extend([p.model_dump() for p in products])

            elif query.collection == "branches":
                branch_results = await self.vector_search.search_branches(
                    query=query.query,
                    limit=query.limit
                )
                # Extract IDs from VectorSearchResult objects
                branch_ids = [r.mongo_id for r in branch_results]
                # Fetch full branch data
                branches = await branches_repo.get_by_ids(branch_ids)
                context.branches.extend([b.model_dump() for b in branches])

            elif query.collection == "businesses":
                business_results = await self.vector_search.search_businesses(
                    query=query.query,
                    limit=query.limit
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
        context: SearchContext
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
        # Build prompt with context
        conversation = self._format_history(history)
        conversation.append(f"User: {message}")

        # Add search context if available
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

        # Add intent analysis
        conversation_text = "\n".join(conversation)
        missing_info_text = ', '.join(intent.missing_info) if intent.missing_info else 'None'
        prompt = f"{conversation_text}\n\nIntent Analysis:\n- Type: {intent.response_type}\n- Reasoning: {intent.reasoning}\n- Missing Info: {missing_info_text}{context_text}"

        # Generate with structured output
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.final_response_system_prompt,
                response_mime_type="application/json",
                response_schema=AiFinalResponse
            )
        )

        # Parse response
        import json
        if not response.text:
            raise ValueError("Empty response from AI model")
        return AiFinalResponse(**json.loads(response.text))

    async def _create_draft_order(
        self,
        session_id: str,
        draft_data: DraftOrderData
    ) -> None:
        """
        Create a draft order in database.

        Args:
            session_id: User session ID
            draft_data: Draft order data from AI
        """
        print(f"\n{'='*80}")
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

        # Calculate totals
        items = []
        subtotal = 0.0
        for i, product in enumerate(products):
            quantity = draft_data.quantities[i] if i < len(draft_data.quantities) else 1
            item_total = product.price * quantity
            subtotal += item_total

            items.append({
                "productId": product.id,
                "name": product.name,
                "price": product.price,
                "quantity": quantity,
                "imageUrl": product.image
            })

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
                    "coordinates": coords  # [longitude, latitude]
                }
            }
            print(f"[AI RAG] Using user's saved location: {coords}")
        # Priority 2: Use delivery address from draft data if provided
        elif draft_data.delivery_address:
            delivery_address = {
                "street": draft_data.delivery_address,
                "reference": draft_data.delivery_reference,
                "coordinates": {
                    "type": "Point",
                    "coordinates": draft_data.delivery_coordinates or [0, 0]
                }
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
            payment_method_id=draft_data.payment_method_id
        )

        print(f"[AI RAG] Draft order created successfully: ID={draft.id}")
        print(f"{'='*80}\n")

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
        """Format products for context."""
        lines = []
        for p in products:
            lines.append(
                f"- ID: {p['id']}, Name: {p['name']}, Price: ${p['price']} {p.get('currency', 'USD')}, "
                f"Branch: {p['branchId']}, Available: {p.get('availability', True)}"
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
