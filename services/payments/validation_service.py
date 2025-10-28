"""Service helpers for validating payment evidence via Gemini OCR."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from models import SmsOcr
from repositories import payments_repo


class GeminiPaymentResponse(BaseModel):
    """Structured response expected from Gemini OCR."""

    quien_envio: str
    banco: str
    fecha: datetime
    es_mensaje_banco: bool
    cantidad_transferida: float
    numero_transferencia: str
    primeros_4_tarjeta: str
    ultimos_4_tarjeta: str

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PaymentValidationResult(BaseModel):
    """Normalized result returned by the validation service."""

    matched: bool
    message: str
    detected_transfer_id: str
    extracted_data: GeminiPaymentResponse
    saved_payment: Optional[SmsOcr] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


async def _extract_gemini_data(
    *, file_bytes: bytes, content_type: str, model_name: str
) -> GeminiPaymentResponse:
    """Send the image bytes to Gemini and parse the structured response."""
    client = genai.Client(api_key=_get_gemini_api_key())

    prompt = """Analiza esta captura de pantalla de un SMS bancario y extrae la siguiente información en formato JSON:

- quien_envio: Remitente del SMS (nombre o número)
- banco: Nombre del banco que envió el mensaje
- fecha: Fecha de la transferencia (formato ISO 8601)
- es_mensaje_banco: true si es un mensaje auténtico de un banco, false si no lo parece
- cantidad_transferida: Monto numérico de la transferencia (solo el número, sin símbolos de moneda)
- numero_transferencia: Número de referencia o ID de la transferencia
- primeros_4_tarjeta: Primeros 4 dígitos de la tarjeta mencionada
- ultimos_4_tarjeta: Últimos 4 dígitos de la tarjeta mencionada

Si algún campo no está disponible en la imagen, usa valores por defecto razonables:
- Para strings: "N/A"
- Para números: 0.0
- Para fecha: usa la fecha actual
- Para es_mensaje_banco: false si no estás seguro
"""

    response = client.models.generate_content(
        model=model_name,
        contents=[
            prompt,
            genai_types.Part.from_bytes(data=file_bytes, mime_type=content_type),
        ],
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiPaymentResponse,
        ),
    )

    try:
        gemini_data = GeminiPaymentResponse.model_validate_json(response.text)
    except ValidationError as exc:
        raise ValueError(f"Error al validar los datos de Gemini: {exc}") from exc

    if not gemini_data.es_mensaje_banco:
        raise ValueError("La imagen no parece ser un SMS bancario válido")

    return gemini_data


def _get_gemini_api_key() -> str:
    """Fetch the Gemini API key from environment variables."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno")
    return api_key


async def validate_payment_image_with_transfer_id(
    *,
    file_bytes: bytes,
    content_type: str,
    transfer_id: str,
    model_name: Optional[str] = None,
) -> PaymentValidationResult:
    """
    Validate a payment evidence image and persist it only if the transfer ID matches.

    Args:
        file_bytes: Raw bytes of the uploaded image.
        content_type: Mime type of the uploaded image.
        transfer_id: Transfer ID provided by the client for comparison.
        model_name: Optional Gemini model override.

    Returns:
        PaymentValidationResult with the comparison outcome and persisted record, if any.
    """
    if not file_bytes:
        raise ValueError("El archivo recibido está vacío")

    transfer_id_normalized = transfer_id.strip()
    if not transfer_id_normalized:
        raise ValueError("El id de transferencia no puede estar vacío")

    selected_model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_data = await _extract_gemini_data(
        file_bytes=file_bytes, content_type=content_type, model_name=selected_model
    )

    detected_transfer_id = (gemini_data.numero_transferencia or "").strip()
    matched = detected_transfer_id == transfer_id_normalized

    saved_payment: Optional[SmsOcr] = None
    if matched:
        payment_payload = gemini_data.model_dump()
        payment_payload["createdAt"] = datetime.utcnow()
        saved_payment = await payments_repo.create(payment_payload)

    message = (
        "El id de transferencia coincide y el pago fue almacenado."
        if matched
        else "El id de transferencia no coincide; no se guardó el pago."
    )

    return PaymentValidationResult(
        matched=matched,
        message=message,
        detected_transfer_id=detected_transfer_id,
        extracted_data=gemini_data,
        saved_payment=saved_payment,
    )
