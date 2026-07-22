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
    """Dump model in python mode and normalize values for Strawberry.

    ⚠️ El resultado suele usarse como `SomeGraphQLType(**to_strawberry_dict(model))`.
    Como esto vuelca TODOS los campos del modelo pydantic, agregar un campo nuevo
    a un modelo de dominio (Business/Branch/Product/...) rompe con
    "unexpected keyword argument" cualquier tipo GraphQL construido así que no
    declare ese campo — y no lo detecta ningún chequeo de sintaxis, solo un
    request real. Usa `exclude={...}` (dump_kwargs) o agrega el campo al tipo
    GraphQL destino antes de dar por segura una migración de modelo. Ver el
    aviso en domain/models.py sobre Business/Branch/Product.
    """
    if hasattr(model, "model_dump"):
        data = model.model_dump(**dump_kwargs)
    elif isinstance(model, dict):
        data = model
    else:
        raise TypeError(
            f"Unsupported model type for to_strawberry_dict: {type(model)!r}"
        )

    return to_strawberry_value(data)
