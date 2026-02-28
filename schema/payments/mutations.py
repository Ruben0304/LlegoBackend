"""GraphQL mutations for payment validation and payment processing."""

import os
from datetime import datetime
from typing import Optional

import strawberry
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError
from strawberry.file_uploads import Upload
from strawberry.types import Info

from repositories import payment_methods_repo, payments_repo
from services.payments_service import payment_service
from utils.graphql_auth import apply_optional_jwt

from .types import (
    InitiatePaymentResult,
    PaymentAttemptType,
    PaymentType,
    payment_attempt_to_type,
)


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
    @strawberry.mutation(
        description="Validar una imagen de transferencia bancaria usando Gemini OCR"
    )
    async def validate_payment_image(
        self, info: Info, file: Upload, jwt: Optional[str] = None
    ) -> PaymentType:
        """
        Procesa una imagen de SMS bancario usando Gemini Vision API.
        Extrae los datos de la transferencia y los guarda en la base de datos.

        Args:
            file: Archivo de imagen (JPEG, PNG, etc.) con la captura del SMS bancario

        Returns:
            PaymentType con los datos extraídos y guardados en la base de datos
        """
        try:
            apply_optional_jwt(jwt, info)
            # Obtener API key y modelo de Gemini desde variables de entorno
            api_key = os.getenv("GEMINI_API_KEY")
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

            if not api_key:
                raise Exception(
                    "GEMINI_API_KEY no está configurada en las variables de entorno"
                )

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
                        data=image_bytes, mime_type=content_type
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
            return PaymentType(**payment.model_dump(mode="json"))

        except Exception as e:
            raise Exception(f"Error al procesar la imagen: {str(e)}")

    # ============================================
    # Payment Processing Mutations
    # ============================================

    @strawberry.mutation(description="Iniciar un pago para un pedido")
    async def initiate_payment(
        self,
        info: Info,
        orderId: str,
        paymentMethodId: str,
        jwt: str,
        includeDeliveryFee: bool = True,
        sendsSmsNotification: bool = False,
    ) -> InitiatePaymentResult:
        """
        Initiate a payment for an order.

        For wallet payments: processes immediately if balance is sufficient.
        For Stripe payments: returns client secret for completing payment in app.
        For manual payments: returns instructions and awaits proof upload.
        For cash payments: awaits delivery person confirmation.

        Args:
            orderId: The order to pay for
            paymentMethodId: The payment method to use
            jwt: User JWT token
            includeDeliveryFee: Whether to include delivery fee in this payment

        Returns:
            Payment attempt with status and any necessary info (client secret, instructions)
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.initiate_payment(
                order_id=orderId,
                payment_method_id=paymentMethodId,
                user_id=user_id,
                include_delivery_fee=includeDeliveryFee,
                sends_sms_notification=sendsSmsNotification,
            )

            # Get payment method for instructions
            payment_method = await payment_methods_repo.get_by_id(paymentMethodId)
            instructions = payment_method.instructions if payment_method else None

            return InitiatePaymentResult(
                paymentAttempt=payment_attempt_to_type(attempt),
                instructions=instructions,
            )

        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(
        description="Confirmar que el cliente envió el pago (para métodos manuales)"
    )
    async def confirm_payment_sent(
        self, info: Info, paymentAttemptId: str, proofUrl: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Customer confirms they sent the payment and uploads proof.

        This is used for manual payment methods like bank transfers.
        After this, the payment awaits business confirmation.

        Args:
            paymentAttemptId: The payment attempt ID
            proofUrl: URL to the uploaded proof/receipt image
            jwt: User JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.confirm_payment_sent(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
                proof_url=proofUrl,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Negocio confirma que recibió el pago")
    async def confirm_payment_received(
        self, info: Info, paymentAttemptId: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Business confirms they received the payment.

        This completes the payment for manual methods.

        Args:
            paymentAttemptId: The payment attempt ID
            jwt: Business user JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.confirm_payment_received(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(
        description="Repartidor confirma que recibió el pago en efectivo"
    )
    async def confirm_cash_received(
        self, info: Info, paymentAttemptId: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Delivery person confirms they received cash payment.

        This completes the payment for cash on delivery orders.

        Args:
            paymentAttemptId: The payment attempt ID
            jwt: Delivery person JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            # For cash payments, the delivery person's user ID is used
            attempt = await payment_service.confirm_cash_received(
                payment_attempt_id=paymentAttemptId,
                delivery_person_id=user_id,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Negocio disputa que no recibió el pago")
    async def dispute_payment(
        self, info: Info, paymentAttemptId: str, reason: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Business disputes that they didn't receive the payment.

        This opens a dispute case for manual payment methods.

        Args:
            paymentAttemptId: The payment attempt ID
            reason: Reason for the dispute
            jwt: Business user JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.dispute_payment(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
                reason=reason,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Solicitar reembolso de un pago")
    async def request_refund(
        self, info: Info, paymentAttemptId: str, reason: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Customer requests a refund for a completed payment.

        Only works for refundable payment methods and orders not yet delivered.

        Args:
            paymentAttemptId: The payment attempt ID
            reason: Reason for the refund request
            jwt: Customer JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.request_refund(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
                reason=reason,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(
        description=(
            "Confirmar automáticamente un pago por transferencia usando el sistema "
            "de Shortcut Transfers. Busca por el teléfono del perfil del usuario; "
            "si no hay coincidencia, el cliente puede proveer el ID de transferencia."
        )
    )
    async def confirm_transfer_by_shortcut(
        self,
        info: Info,
        paymentAttemptId: str,
        jwt: str,
        transferId: Optional[str] = None,
    ) -> PaymentAttemptType:
        """
        Auto-confirm a transfer payment via registered Shortcut Transfer.

        If transferId is omitted, the user's profile phone number is used to
        match a pending shortcut transfer.  If no match is found that way, the
        client should prompt the user for their bank transfer reference ID and
        call this mutation again passing that value as transferId.

        Raises:
            Exception("phone_not_found") when no pending transfer matches the
            user's phone — the client should surface the manual-ID fallback.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.confirm_transfer_by_shortcut(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
                transfer_id=transferId,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))

    @strawberry.mutation(description="Cancelar un intento de pago pendiente")
    async def cancel_payment(
        self, info: Info, paymentAttemptId: str, jwt: str
    ) -> PaymentAttemptType:
        """
        Cancel a pending payment attempt.

        Only works for payments that haven't been completed yet.

        Args:
            paymentAttemptId: The payment attempt ID
            jwt: Customer JWT token
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        try:
            attempt = await payment_service.cancel_payment(
                payment_attempt_id=paymentAttemptId,
                user_id=user_id,
            )
            return payment_attempt_to_type(attempt)
        except ValueError as e:
            raise Exception(str(e))
