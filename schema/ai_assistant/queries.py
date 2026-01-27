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

        try:
            # Initialize AI RAG service
            ai_service = AiRagService()

            # Process message with RAG
            response = await ai_service.send_message(
                message=input.message,
                session_id=user_id  # Use user_id from JWT as session_id
            )

            # Convert suggested products to GraphQL types
            suggested_products = []
            for suggestion in response.suggested_products:
                product = await products_repo.get_by_id(suggestion.product_id)
                if product:
                    suggested_products.append(
                        ProductSuggestionType(
                            product=ProductType(**product.model_dump()),
                            reason=suggestion.reason
                        )
                    )

            # Convert suggested branches to GraphQL types
            suggested_branches = []
            for suggestion in response.suggested_branches:
                branch = await branches_repo.get_by_id(suggestion.branch_id)
                if branch:
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

            # Convert draft order if present
            draft_order = None
            if response.draft_order:
                # Fetch the created draft from database
                drafts = await draft_orders_repo.get_pending_by_session(user_id)
                if drafts:
                    latest_draft = drafts[0]  # Most recent
                    draft_order = DraftOrderType(
                        id=latest_draft.id,
                        session_id=latest_draft.sessionId,
                        customer_id=latest_draft.customerId,
                        branch_id=latest_draft.branchId,
                        business_id=latest_draft.businessId,
                        items=[
                            DraftOrderItemType(
                                product_id=item["productId"],
                                name=item["name"],
                                price=item["price"],
                                quantity=item["quantity"],
                                image_url=item["imageUrl"]
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

            # Return GraphQL response
            return AiAssistantResponseType(
                response_type=response.response_type,
                ai_text=response.ai_text,
                suggested_products=suggested_products,
                suggested_branches=suggested_branches,
                draft_order=draft_order,
                missing_fields=response.missing_fields,
                confidence=response.confidence
            )

        except Exception as e:
            print(f"Error in AI chat: {e}")
            import traceback
            traceback.print_exc()
            return None
