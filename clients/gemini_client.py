"""Gemini client singleton."""
from typing import Optional
from google import genai
from core.config import settings

# Global Gemini client instance
gemini_client: Optional[genai.Client] = None


def connect_to_gemini():
    """Initialize Gemini client"""
    global gemini_client
    try:
        gemini_client = genai.Client(api_key=settings.gemini_api_key)
        print(f"✓ Connected to Gemini API (model: {settings.gemini_model})")
    except Exception as e:
        print(f"✗ Error connecting to Gemini: {e}")
        raise


def close_gemini_connection():
    """Close Gemini connection"""
    global gemini_client
    if gemini_client:
        gemini_client = None
        print("✓ Gemini connection closed")


def get_gemini_client() -> genai.Client:
    """Get Gemini client instance"""
    if gemini_client is None:
        raise RuntimeError("Gemini client not initialized. Call connect_to_gemini() first.")
    return gemini_client
