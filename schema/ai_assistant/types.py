"""GraphQL type definitions for AI Assistant entity."""
import strawberry
from typing import List, Union, Optional
from schema.products.types import ProductType
from schema.branches.types import BranchType


@strawberry.type
class PaymentMethodType:
    """Payment method type."""
    id: str = strawberry.field(description="Payment method ID")
    currency: str = strawberry.field(description="Currency (e.g., CUP, USD)")
    method: str = strawberry.field(description="Payment method (e.g., tarjeta, efectivo, transferencia)")


# Union type for different entity types returned by AI
EntityType = strawberry.union("EntityType", [ProductType, BranchType, PaymentMethodType])


@strawberry.type
class AiAssistantOutputType:
    """AI Assistant output containing response details."""
    type: str = strawberry.field(description="Type of response (e.g., 'payment_method', 'products', 'branches')")
    ai_text: str = strawberry.field(description="AI-generated response text", name="AItext")
    ids: List[str] = strawberry.field(description="List of relevant IDs (for debugging)")
    entities: Optional[List[EntityType]] = strawberry.field(
        description="List of resolved entities (products, branches, or payment methods)",
        default=None
    )


@strawberry.type
class AiAssistantResponseType:
    """Complete AI Assistant response."""
    output: AiAssistantOutputType = strawberry.field(description="Response output from AI assistant")


@strawberry.input
class AiAssistantChatInput:
    """Input for sending a message to the AI assistant."""
    message: str = strawberry.field(description="The user message/query to send")
    session_id: str = strawberry.field(description="Session ID for conversation context")
