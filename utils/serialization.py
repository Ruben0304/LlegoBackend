"""Helpers for serializing Pydantic models into Strawberry-friendly values."""

from datetime import date, datetime, time
from typing import Any

from bson import ObjectId


def to_strawberry_value(value: Any) -> Any:
    """Convert nested values for Strawberry while preserving datetimes."""
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value

    if isinstance(value, dict):
        return {key: to_strawberry_value(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_strawberry_value(item) for item in value]

    return value


def to_strawberry_dict(model: Any, **dump_kwargs: Any) -> dict:
    """Dump model in python mode and normalize values for Strawberry."""
    if hasattr(model, "model_dump"):
        data = model.model_dump(**dump_kwargs)
    elif isinstance(model, dict):
        data = model
    else:
        raise TypeError(
            f"Unsupported model type for to_strawberry_dict: {type(model)!r}"
        )

    return to_strawberry_value(data)
