"""Gemini embedding service for generating vector representations."""
from typing import List, Optional
from google.genai import types
from core.config import settings
from clients import get_gemini_client


class GeminiEmbeddingService:
    """Service for generating embeddings using Gemini API."""

    def __init__(self):
        """Initialize Gemini service with settings."""
        self.client = get_gemini_client()
        self.model = settings.gemini_model
        self.dimension = settings.embedding_dimension

    def generate_embedding(
        self,
        text: str,
        task_type: Optional[str] = None
    ) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            task_type: Task type for optimization (default: RETRIEVAL_DOCUMENT)

        Returns:
            List of float values representing the embedding
        """
        if not task_type:
            task_type = settings.embedding_task_type

        result = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.dimension
            )
        )

        return result.embeddings[0].values

    def generate_embeddings_batch(
        self,
        texts: List[str],
        task_type: Optional[str] = None
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single request.

        Args:
            texts: List of texts to embed
            task_type: Task type for optimization

        Returns:
            List of embeddings
        """
        if not texts:
            return []

        if not task_type:
            task_type = settings.embedding_task_type

        result = self.client.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.dimension
            )
        )

        return [embedding.values for embedding in result.embeddings]
