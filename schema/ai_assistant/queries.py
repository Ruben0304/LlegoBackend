"""GraphQL query resolvers for AI Assistant."""
import strawberry
from typing import Optional
from strawberry.types import Info
from schema.products.types import ProductType
from schema.branches.types import BranchType, CoordinatesType, BranchTipo
from .types import (
    AiAssistantResponseType,
    AiAssistantChatInput,
    ProductSuggestionType,
    BranchSuggestionType,
    DraftOrderType,
    DraftOrderItemType,
)
from services.ai_rag_service import AiRagService
from models import products_repo, branches_repo, draft_orders_repo
from utils.graphql_auth import require_auth
from utils.rate_limit import rate_limit_graphql


@strawberry.type
class AiAssistantQuery:
    @strawberry.field(description="Send a message to the AI assistant and get a response with RAG")
    async def ai_chat(
        self,
        info: Info,
        input: AiAssistantChatInput,
        jwt: Optional[str] = None
    ) -> Optional[AiAssistantResponseType]:
        """Send a message to the AI assistant with RAG support."""
        user_id = require_auth(jwt, info)  # JWT is required, get user_id as session_id
        rate_limit_graphql(info, "ai")  # 2/min - very expensive (Gemini API)

        print(f"\n{'='*80}")
        print(f"[AI CHAT] Received message from user: {user_id}")
        print(f"[AI CHAT] Message: {input.message}")

        try:
            # Initialize AI RAG service
            ai_service = AiRagService()

            # Process message with RAG
            response = await ai_service.send_message(
                message=input.message,
                session_id=user_id  # Use user_id from JWT as session_id
            )

            print(f"[AI CHAT] Response from AI service:")
            print(f"[AI CHAT]   - response_type: {response.response_type}")
            print(f"[AI CHAT]   - ai_text: {response.ai_text}")
            print(f"[AI CHAT]   - suggested_products: {len(response.suggested_products)} items")
            print(f"[AI CHAT]   - suggested_branches: {len(response.suggested_branches)} items")
            print(f"[AI CHAT]   - draft_order: {response.draft_order}")
            print(f"[AI CHAT]   - missing_fields: {response.missing_fields}")
            print(f"[AI CHAT]   - confidence: {response.confidence}")

            # Convert suggested products to GraphQL types
            suggested_products = []
            print(f"[AI CHAT] Converting {len(response.suggested_products)} product suggestions...")
            for i, suggestion in enumerate(response.suggested_products):
                print(f"[AI CHAT]   Product {i+1}: ID={suggestion.product_id}, reason={suggestion.reason}")
                product = await products_repo.get_by_id(suggestion.product_id)
                if product:
                    print(f"[AI CHAT]   Product found: {product.name} (${product.price})")
                    suggested_products.append(
                        ProductSuggestionType(
                            product=ProductType(**product.model_dump()),
                            reason=suggestion.reason
                        )
                    )
                else:
                    print(f"[AI CHAT]   WARNING: Product not found in database!")

            # Convert suggested branches to GraphQL types
            suggested_branches = []
            print(f"[AI CHAT] Converting {len(response.suggested_branches)} branch suggestions...")
            for i, suggestion in enumerate(response.suggested_branches):
                print(f"[AI CHAT]   Branch {i+1}: ID={suggestion.branch_id}, reason={suggestion.reason}")
                branch = await branches_repo.get_by_id(suggestion.branch_id)
                if branch:
                    print(f"[AI CHAT]   Branch found: {branch.name} at {branch.address}")
                    print(f"[AI CHAT]   Branch coords: {branch.coordinates.model_dump()}")
                    print(f"[AI CHAT]   Branch tipos: {branch.tipos}")
                    # Convert branch to BranchType with proper coordinate handling
                    branch_type = BranchType(
                        **{
                            **branch.model_dump(),
                            'coordinates': CoordinatesType(**branch.coordinates.model_dump()),
                            'tipos': [BranchTipo(t) for t in (branch.tipos or [])]
                        }
                    )
                    suggested_branches.append(
                        BranchSuggestionType(
                            branch=branch_type,
                            reason=suggestion.reason
                        )
                    )
                else:
                    print(f"[AI CHAT]   WARNING: Branch not found in database!")

            # Convert draft order if present
            draft_order = None
            if response.draft_order:
                print(f"[AI CHAT] Draft order creation detected, fetching from database...")
                # Fetch the created draft from database
                drafts = await draft_orders_repo.get_pending_by_session(user_id)
                print(f"[AI CHAT] Found {len(drafts) if drafts else 0} pending drafts for user")
                if drafts:
                    latest_draft = drafts[0]  # Most recent
                    print(f"[AI CHAT] Latest draft order:")
                    print(f"[AI CHAT]   - ID: {latest_draft.id}")
                    print(f"[AI CHAT]   - Branch: {latest_draft.branchId}")
                    print(f"[AI CHAT]   - Business: {latest_draft.businessId}")
                    print(f"[AI CHAT]   - Items: {len(latest_draft.items)} products")
                    print(f"[AI CHAT]   - Subtotal: ${latest_draft.subtotal}")
                    print(f"[AI CHAT]   - Delivery fee: ${latest_draft.deliveryFee}")
                    print(f"[AI CHAT]   - Total: ${latest_draft.total}")
                    print(f"[AI CHAT]   - Delivery address: {latest_draft.deliveryAddress}")
                    print(f"[AI CHAT]   - Payment method: {latest_draft.paymentMethodId}")
                    print(f"[AI CHAT]   - Status: {latest_draft.status}")

                    draft_order = DraftOrderType(
                        id=latest_draft.id,
                        session_id=latest_draft.sessionId,
                        customer_id=latest_draft.customerId,
                        branch_id=latest_draft.branchId,
                        business_id=latest_draft.businessId,
                        items=[
                            DraftOrderItemType(
                                product_id=item.productId,
                                name=item.name,
                                price=item.price,
                                quantity=item.quantity,
                                image_url=item.imageUrl
                            )
                            for item in latest_draft.items
                        ],
                        subtotal=latest_draft.subtotal,
                        delivery_fee=latest_draft.deliveryFee,
                        total=latest_draft.total,
                        currency=latest_draft.currency,
                        delivery_address=str(latest_draft.deliveryAddress) if latest_draft.deliveryAddress else None,
                        payment_method_id=latest_draft.paymentMethodId,
                        status=latest_draft.status,
                        created_at=latest_draft.createdAt,
                        expires_at=latest_draft.expiresAt
                    )
                else:
                    print(f"[AI CHAT]   WARNING: Draft order was supposed to be created but not found!")
            else:
                print(f"[AI CHAT] No draft order in response")

            # Return GraphQL response
            graphql_response = AiAssistantResponseType(
                response_type=response.response_type,
                ai_text=response.ai_text,
                suggested_products=suggested_products,
                suggested_branches=suggested_branches,
                draft_order=draft_order,
                missing_fields=response.missing_fields,
                confidence=response.confidence
            )

            print(f"[AI CHAT] Final GraphQL response:")
            print(f"[AI CHAT]   - response_type: {graphql_response.response_type}")
            print(f"[AI CHAT]   - ai_text length: {len(graphql_response.ai_text)} chars")
            print(f"[AI CHAT]   - suggested_products: {len(graphql_response.suggested_products)} items")
            print(f"[AI CHAT]   - suggested_branches: {len(graphql_response.suggested_branches)} items")
            print(f"[AI CHAT]   - draft_order present: {graphql_response.draft_order is not None}")
            print(f"[AI CHAT]   - missing_fields: {graphql_response.missing_fields}")
            print(f"[AI CHAT]   - confidence: {graphql_response.confidence}")
            print(f"{'='*80}\n")

            return graphql_response

        except Exception as e:
            print(f"[AI CHAT] ERROR in AI chat: {e}")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
            return None
