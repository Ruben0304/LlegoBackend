"""Custom Pydantic type for MongoDB ObjectId.

This module provides a PyObjectId type that can be used with Pydantic models
to seamlessly work with MongoDB ObjectIds while maintaining type safety.
"""
from typing import Any
from bson import ObjectId
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """
    Custom ObjectId type for Pydantic v2.

    Allows Pydantic models to use ObjectId fields seamlessly,
    handling validation and serialization automatically.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define how Pydantic should validate and serialize this type."""

        def validate(value: Any) -> ObjectId:
            """Validate and convert various inputs to ObjectId."""
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str):
                if not ObjectId.is_valid(value):
                    raise ValueError(f"Invalid ObjectId: {value}")
                return ObjectId(value)
            if isinstance(value, bytes):
                return ObjectId(value)
            raise ValueError(f"Cannot convert {type(value)} to ObjectId")

        return core_schema.with_info_plain_validator_function(
            lambda v, _: validate(v),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x),
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def __get_validators__(cls):
        """For Pydantic v1 compatibility (if needed)."""
        yield cls.validate

    @classmethod
    def validate(cls, v):
        """Validate for Pydantic v1."""
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid ObjectId")
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")
