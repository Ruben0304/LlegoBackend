"""GraphQL query resolvers for AI Assistant."""
import strawberry
from typing import Optional

from .types import AiAssistantResponseType, AiAssistantOutputType, AiAssistantChatInput
from services.ai_assistant_service import AiAssistantService


@strawberry.type
class AiAssistantQuery:
    @strawberry.field(description="Send a message to the AI assistant and get a response")
    async def ai_chat(self, input: AiAssistantChatInput) -> Optional[AiAssistantResponseType]:
        """
        Send a message to the AI assistant.

        The assistant can help with:
        - Payment method inquiries
        - Product recommendations
        - General queries about businesses

        Args:
            input: Message and session ID

        Returns:
            AI assistant response with type, text, and relevant IDs
        """
        try:
            ai_service = AiAssistantService()
            response = await ai_service.send_message(
                message=input.message,
                session_id=input.session_id
            )

            # Convert Pydantic model to Strawberry type
            output_data = response.output.model_dump()
            return AiAssistantResponseType(
                output=AiAssistantOutputType(
                    type=output_data["type"],
                    ai_text=output_data["AItext"],
                    ids=output_data["ids"]
                )
            )
        except Exception as e:
            print(f"Error in AI chat: {e}")
            return None
