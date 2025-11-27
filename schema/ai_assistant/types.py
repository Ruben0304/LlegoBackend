"""GraphQL type definitions for AI Assistant entity."""
import strawberry
from typing import List


@strawberry.type
class AiAssistantOutputType:
    """AI Assistant output containing response details."""
    type: str = strawberry.field(description="Type of response (e.g., 'payment_method', 'product_search')")
    ai_text: str = strawberry.field(description="AI-generated response text", name="AItext")
    ids: List[str] = strawberry.field(description="List of relevant IDs (products, branches, etc.)")


@strawberry.type
class AiAssistantResponseType:
    """Complete AI Assistant response."""
    output: AiAssistantOutputType = strawberry.field(description="Response output from AI assistant")


@strawberry.input
class AiAssistantChatInput:
    """Input for sending a message to the AI assistant."""
    message: str = strawberry.field(description="The user message/query to send")
    session_id: str = strawberry.field(description="Session ID for conversation context")
