"""Utility functions for Wallet operations."""
from bson import ObjectId


def to_object_id(id_str: str):
    """Convert string ID to ObjectId if possible, otherwise return as is."""
    try:
        return ObjectId(id_str)
    except Exception:
        return id_str
