"""GraphQL mutations for payment validation using Gemini OCR."""
import strawberry
import os
from datetime import datetime
from pydantic import BaseModel, ValidationError
from strawberry.file_uploads import Upload
from google import genai
from google.genai import types as genai_types

from .types import PaymentType
from repositories import payments_repo


# Modelo Pydantic para la respuesta de Gemini (sin el id y createdAt)
class GeminiPaymentResponse(BaseModel):
    quien_envio: str
    banco: str
    fecha: datetime
    es_mensaje_banco: bool
    cantidad_transferida: float
    numero_transferencia: str
    primeros_4_tarjeta: str
    ultimos_4_tarjeta: str


@strawberry.type
class PaymentMutation:
    @strawberry.mutation(description="Validar una imagen de transferencia bancaria usando Gemini OCR")
    async def validate_payment_image(self, file: Upload) -> PaymentType:
        """
        Procesa una imagen de SMS bancario usando Gemini Vision API.
        Extrae los datos de la transferencia y los guarda en la base de datos.

        Args:
            file: Archivo de imagen (JPEG, PNG, etc.) con la captura del SMS bancario

        Returns:
            PaymentType con los datos extraídos y guardados en la base de datos
        """
        try:
            # Obtener API key y modelo de Gemini desde variables de entorno
            api_key = os.getenv("GEMINI_API_KEY")
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

            if not api_key:
                raise Exception("GEMINI_API_KEY no está configurada en las variables de entorno")

            # Crear cliente de Gemini
            client = genai.Client(api_key=api_key)

            # Leer los bytes del archivo subido
            image_bytes = await file.read()

            # Obtener el content type del archivo (ej: image/jpeg, image/png)
            content_type = file.content_type or "image/jpeg"

            # Prompt para Gemini
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

            # Enviar la imagen a Gemini
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    prompt,
                    genai_types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=content_type
                    ),
                ],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiPaymentResponse,
                ),
            )

            # Validar la respuesta con Pydantic
            try:
                gemini_data = GeminiPaymentResponse.model_validate_json(response.text)
            except ValidationError as e:
                raise Exception(f"Error al validar los datos de Gemini: {str(e)}")

            # Verificar que sea un mensaje bancario válido
            if not gemini_data.es_mensaje_banco:
                raise Exception("La imagen no parece ser un SMS bancario válido")

            # Preparar datos para guardar en MongoDB
            payment_data = gemini_data.model_dump()
            payment_data["createdAt"] = datetime.utcnow()

            # Guardar en la base de datos
            payment = await payments_repo.create(payment_data)

            # Retornar el tipo GraphQL
            return PaymentType(**payment.model_dump())

        except Exception as e:
            raise Exception(f"Error al procesar la imagen: {str(e)}")
