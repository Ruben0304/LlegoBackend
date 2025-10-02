"""Clients module exports."""
from clients.mongodb_client import get_database, connect_to_mongo, close_mongo_connection
from clients.qdrant_client import get_qdrant_client, connect_to_qdrant, close_qdrant_connection, create_collection
from clients.gemini_client import get_gemini_client, connect_to_gemini, close_gemini_connection
from clients.lifespan import lifespan

__all__ = [
    # MongoDB
    "get_database",
    "connect_to_mongo",
    "close_mongo_connection",
    # Qdrant
    "get_qdrant_client",
    "connect_to_qdrant",
    "close_qdrant_connection",
    "create_collection",
    # Gemini
    "get_gemini_client",
    "connect_to_gemini",
    "close_gemini_connection",
    # Lifespan
    "lifespan",
]
