"""Los fallos internos no llegan al cliente; los mensajes de negocio sí.

MaskUnexpectedErrors sustituye por un mensaje genérico los errores de tipo
"inesperado" (AttributeError, KeyError, Mongo, red...) y los Exception que repiten su
texto, pero conserva original_error para que ErrorLoggingExtension siga registrando
el fallo real. Sin MongoDB: schema mínimo con la extensión real.
"""

import asyncio
import os
from typing import List

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest
import strawberry
from pymongo.errors import ServerSelectionTimeoutError
from strawberry.extensions import SchemaExtension

from schema.extensions import UNEXPECTED_ERROR_MESSAGE, MaskUnexpectedErrors
from services.courier_access import CourierNotApprovedError

CAPTURED: List = []


class _CaptureOriginals(SchemaExtension):
    """Como ErrorLoggingExtension: lee original_error en on_request_end."""

    def on_request_end(self) -> None:
        result = self.execution_context.result
        if result is None:  # error de validación: no llega a ejecutarse
            return
        CAPTURED.extend(e.original_error for e in (result.errors or []))


def _wrap_key_error():
    try:
        {}["campo_interno"]
    except KeyError as e:
        raise Exception(f"Error al crear el pedido: {e}")


def _business_message_inside_except():
    try:
        {}["x"]
    except KeyError:
        raise Exception("Pedido no encontrado")


@strawberry.type
class _Query:
    @strawberry.field
    def attribute_error(self) -> str:
        return None.value  # type: ignore[attr-defined]

    @strawberry.field
    def mongo_down(self) -> str:
        raise ServerSelectionTimeoutError("localhost:27017: [Errno 61] Connection refused")

    @strawberry.field
    def wrapped_internal(self) -> str:
        _wrap_key_error()
        return ""

    @strawberry.field
    def business_exception(self) -> str:
        raise Exception("No autorizado")

    @strawberry.field
    def business_value_error(self) -> str:
        raise ValueError("Ya tienes un pedido en curso")

    @strawberry.field
    def courier_not_approved(self) -> str:
        raise CourierNotApprovedError()

    @strawberry.field
    def business_runtime_error(self) -> str:
        raise RuntimeError("Balance insuficiente en cuenta de plataforma")

    @strawberry.field
    def business_message_raised_while_handling(self) -> str:
        _business_message_inside_except()
        return ""


_schema = strawberry.Schema(query=_Query, extensions=[_CaptureOriginals, MaskUnexpectedErrors])


def _run(field):
    CAPTURED.clear()
    result = asyncio.run(_schema.execute("{ %s }" % field))
    assert result.errors and len(result.errors) == 1
    return result.errors[0]


@pytest.mark.parametrize("field", ["attributeError", "mongoDown", "wrappedInternal"])
def test_internal_failures_are_masked_but_still_logged(field):
    error = _run(field)

    assert error.message == UNEXPECTED_ERROR_MESSAGE
    assert "campo_interno" not in error.formatted["message"]
    assert error.formatted.get("extensions") in (None, {})
    # El log (ErrorLoggingExtension) sigue viendo el fallo real.
    assert CAPTURED and CAPTURED[0] is not None


@pytest.mark.parametrize(
    "field,message",
    [
        ("businessException", "No autorizado"),
        ("businessValueError", "Ya tienes un pedido en curso"),
        ("businessRuntimeError", "Balance insuficiente en cuenta de plataforma"),
        ("businessMessageRaisedWhileHandling", "Pedido no encontrado"),
    ],
)
def test_business_messages_reach_the_client(field, message):
    assert _run(field).message == message


def test_courier_not_approved_keeps_message_and_code():
    error = _run("courierNotApproved")
    assert error.message.startswith("COURIER_NOT_APPROVED")
    assert error.formatted["extensions"]["code"] == "COURIER_NOT_APPROVED"


def test_query_validation_errors_are_not_masked():
    result = asyncio.run(_schema.execute("{ campoQueNoExiste }"))
    assert "campoQueNoExiste" in result.errors[0].message
