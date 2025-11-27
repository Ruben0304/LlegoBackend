"""AI Assistant service for n8n webhook integration."""
from typing import List, Optional
import httpx
from pydantic import BaseModel


class AiAssistantOutput(BaseModel):
    """Response output from AI assistant."""
    type: str
    AItext: str
    ids: List[str]


class AiAssistantResponse(BaseModel):
    """Complete response from AI assistant webhook."""
    output: AiAssistantOutput


class AiAssistantService:
    """Service for interacting with n8n AI assistant webhook."""

    def __init__(self):
        """Initialize AI assistant service."""
        self.webhook_url = "https://primary-production-f9ab.up.railway.app/webhook/search"
        self.timeout = 30.0  # 30 seconds timeout

    async def send_message(
        self,
        message: str,
        session_id: str
    ) -> AiAssistantResponse:
        """
        Send a message to the AI assistant webhook.

        Args:
            message: The user message/query to send
            session_id: Session identifier for conversation context

        Returns:
            AiAssistantResponse with output containing type, AItext, and ids

        Raises:
            httpx.HTTPError: If the request fails
        """
        params = {
            "message": message,
            "session_ID": session_id
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.webhook_url,
                params=params
            )
            response.raise_for_status()

            # Parse and validate response
            data = response.json()
            return AiAssistantResponse(**data)

    async def get_payment_alternatives(
        self,
        message: str,
        session_id: str
    ) -> Optional[AiAssistantResponse]:
        """
        Get payment alternatives from AI assistant.

        Convenience method that calls send_message and checks if type is 'payment_method'.

        Args:
            message: The user message/query
            session_id: Session identifier

        Returns:
            AiAssistantResponse if successful, None if error occurs
        """
        try:
            response = await self.send_message(message, session_id)
            if response.output.type == "payment_method":
                return response
            return response
        except Exception as e:
            print(f"Error getting payment alternatives: {e}")
            return None
