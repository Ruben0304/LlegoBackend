"""GraphQL query resolvers for AI Assistant."""
import strawberry
from typing import Optional, List
from strawberry.types import Info
from schema.products.types import ProductType
from schema.branches.types import BranchType
from .types import (
    AiAssistantResponseType,
    AiAssistantOutputType,
    AiAssistantChatInput,
    PaymentMethodType,
    EntityType,
)
from services.ai_assistant_service import AiAssistantService
from models import products_repo, branches_repo, payment_methods_repo
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class AiAssistantQuery:
    @strawberry.field(description="Send a message to the AI assistant and get a response")
    async def ai_chat(
        self,
        info: Info,
        input: AiAssistantChatInput,
        jwt: Optional[str] = None
    ) -> Optional[AiAssistantResponseType]:
        """
        Send a message to the AI assistant.

        The assistant can help with:
        - Payment method inquiries
        - Product recommendations
        - General queries about businesses

        Args:
            input: Message and session ID

        Returns:
            AI assistant response with type, text, relevant IDs, and resolved entities
        """
        apply_optional_jwt(jwt, info)
        try:
            ai_service = AiAssistantService()
            response = await ai_service.send_message(
                message=input.message,
                session_id=input.session_id
            )

            # Convert Pydantic model to dict
            output_data = response.output.model_dump()
            response_type = output_data["type"]
            ids = output_data["ids"]

            # Fetch entities based on type using switch case pattern
            entities: List[EntityType] = []

            if response_type == "payment_method":
                # Fetch payment methods
                payment_methods = await payment_methods_repo.get_by_ids(ids)
                entities = [
                    PaymentMethodType(
                        id=pm.id,
                        currency=pm.currency,
                        method=pm.method
                    )
                    for pm in payment_methods
                ]

            elif response_type == "products":
                # Fetch products
                products = await products_repo.get_by_ids(ids)
                entities = [
                    ProductType(**p.model_dump())
                    for p in products
                ]

            elif response_type == "branches":
                # Fetch branches
                branches = await branches_repo.get_by_ids(ids)
                entities = [
                    BranchType(**b.model_dump())
                    for b in branches
                ]

            # Return response with resolved entities
            return AiAssistantResponseType(
                output=AiAssistantOutputType(
                    type=response_type,
                    ai_text=output_data["AItext"],
                    ids=ids,
                    entities=entities if entities else None
                )
            )
        except Exception as e:
            print(f"Error in AI chat: {e}")
            import traceback
            traceback.print_exc()
            return None
