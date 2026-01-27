"""Chat memory repository for AI assistant conversations."""
from typing import List, Dict, Any
from datetime import datetime
from clients import get_database
from models import ChatMessage


class ChatMemoryRepository:
    """Repository for managing AI assistant chat memory in MongoDB."""

    collection_name = "chat_messages"

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> ChatMessage:
        """
        Add a message to chat memory.

        Args:
            session_id: User ID from JWT (session identifier)
            role: Message role ("user" or "assistant")
            content: Message content

        Returns:
            ChatMessage object
        """
        db = get_database()

        new_message = {
            "sessionId": session_id,
            "role": role,
            "content": content,
            "createdAt": datetime.utcnow()
        }

        result = await db[self.collection_name].insert_one(new_message)
        new_message["_id"] = result.inserted_id

        return ChatMessage(**self._convert_id(new_message))

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[ChatMessage]:
        """
        Get conversation history for a session.

        Args:
            session_id: User ID from JWT
            limit: Maximum number of messages to retrieve (default: 20)

        Returns:
            List of ChatMessage objects, sorted by creation time (oldest first)
        """
        db = get_database()

        # Get last N messages, sorted by creation time descending
        cursor = db[self.collection_name].find(
            {"sessionId": session_id}
        ).sort("createdAt", -1).limit(limit)

        messages = await cursor.to_list(length=limit)

        # Reverse to get chronological order (oldest first)
        messages.reverse()

        return [ChatMessage(**self._convert_id(msg)) for msg in messages]

    async def clear_conversation(self, session_id: str) -> int:
        """
        Clear all messages for a session.

        Args:
            session_id: User ID from JWT

        Returns:
            Number of deleted messages
        """
        db = get_database()
        result = await db[self.collection_name].delete_many({"sessionId": session_id})
        return result.deleted_count

    async def delete_old_messages(self, days: int = 30) -> int:
        """
        Delete messages older than specified days.

        Args:
            days: Number of days to keep (default: 30)

        Returns:
            Number of deleted messages
        """
        db = get_database()
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)
        result = await db[self.collection_name].delete_many(
            {"createdAt": {"$lt": cutoff_date}}
        )
        return result.deleted_count

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ObjectId to string."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
