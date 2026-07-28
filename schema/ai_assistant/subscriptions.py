"""GraphQL subscription resolvers for AI Assistant streaming."""

import re
from typing import AsyncGenerator, Optional

import strawberry
from strawberry.types import Info

from services.ai_quota_service import ai_quota_service
from services.ai_rag_service import get_ai_rag_service
from utils.graphql_auth import require_auth
from utils.rate_limit import rate_limit_graphql

from .types import (
    AiAssistantChatInput,
    AiChatError,
    AiChatErrorCode,
    AiChatQuotaInfo,
    AiChatStreamChunk,
)


@strawberry.type
class AiAssistantSubscription:
    @strawberry.subscription(
        description="Stream AI assistant responses in real-time with RAG support"
    )
    async def ai_chat_stream(
        self, info: Info, input: AiAssistantChatInput, jwt: Optional[str] = None
    ) -> AsyncGenerator[AiChatStreamChunk, None]:
        """
        Stream AI assistant responses in real-time.

        This subscription provides incremental text updates as the AI generates
        the response, followed by reference IDs in the final chunk.
        """
        max_words = 30

        print(f"\n{'=' * 80}")
        print(f"[AI CHAT STREAM] Starting streaming session")
        print(f"[AI CHAT STREAM] Message: {input.message}")

        try:
            # Authentication
            try:
                user_id = require_auth(jwt, info)
            except Exception as e:
                print(f"[AI CHAT STREAM] Authentication failed: {e}")
                print(f"{'=' * 80}\n")
                yield AiChatStreamChunk(
                    delta="",
                    accumulated_text="",
                    is_final=True,
                    error=AiChatError(
                        code=AiChatErrorCode.AI_INVALID_REQUEST,
                        message="Autenticación requerida. Proporciona un JWT válido.",
                    ),
                )
                return

            print(f"[AI CHAT STREAM] User authenticated: {user_id}")

            # Rate limiting
            try:
                rate_limit_graphql(info, "graphql")
            except Exception as e:
                print(f"[AI CHAT STREAM] Rate limit exceeded: {e}")
                print(f"{'=' * 80}\n")
                yield AiChatStreamChunk(
                    delta="",
                    accumulated_text="",
                    is_final=True,
                    error=AiChatError(
                        code=AiChatErrorCode.AI_RATE_LIMIT_EXCEEDED,
                        message="Demasiadas solicitudes. Por favor espera un momento.",
                        retry_after=60,
                    ),
                )
                return

            # Message validation
            words_count = len(re.findall(r"\S+", input.message or ""))
            if words_count > max_words:
                print(
                    f"[AI CHAT STREAM] Message too long: {words_count} words (max: {max_words})"
                )
                print(f"{'=' * 80}\n")
                yield AiChatStreamChunk(
                    delta="",
                    accumulated_text="",
                    is_final=True,
                    error=AiChatError(
                        code=AiChatErrorCode.AI_MESSAGE_TOO_LONG,
                        message=f"El mensaje supera el máximo permitido de {max_words} palabras",
                        max_words=max_words,
                        words_count=words_count,
                    ),
                )
                return

            # Device ID and quota check
            request = (
                info.context.get("request") if isinstance(info.context, dict) else None
            )
            header_device_id = request.headers.get("x-device-id") if request else None
            device_id = input.device_id or header_device_id

            quota = await ai_quota_service.check_and_consume(
                user_id=user_id, device_id=device_id
            )
            if not quota.allowed:
                print(f"[AI CHAT STREAM] Quota exceeded: {quota.reason}")
                print(
                    f"[AI CHAT STREAM] Quota info: {quota.used}/{quota.limit} ({quota.source})"
                )
                print(f"{'=' * 80}\n")

                # Map error code to enum
                error_code_map = {
                    "AI_DEVICE_ID_REQUIRED": AiChatErrorCode.AI_DEVICE_ID_REQUIRED,
                    "AI_DAILY_DEVICE_QUOTA_EXCEEDED": AiChatErrorCode.AI_DAILY_DEVICE_QUOTA_EXCEEDED,
                    "AI_QUOTA_EXCEEDED": AiChatErrorCode.AI_QUOTA_EXCEEDED,
                    "AI_FREE_QUOTA_EXCEEDED": AiChatErrorCode.AI_FREE_QUOTA_EXCEEDED,
                }
                error_code = error_code_map.get(
                    quota.error_code, AiChatErrorCode.AI_QUOTA_EXCEEDED
                )

                yield AiChatStreamChunk(
                    delta="",
                    accumulated_text="",
                    is_final=True,
                    error=AiChatError(
                        code=error_code,
                        message=quota.reason or "Límite de consultas AI alcanzado",
                        quota=AiChatQuotaInfo(
                            source=quota.source,
                            limit=quota.limit,
                            used=quota.used,
                            remaining=quota.remaining,
                        ),
                        retry_after=86400
                        if "diario" in quota.source.lower()
                        or "daily" in quota.source.lower()
                        else None,
                    ),
                )
                return

            print(
                f"[AI CHAT STREAM] Quota consumed: source={quota.source}, used={quota.used}/{quota.limit}"
            )

            # Shared AI RAG service (built once, reused across requests)
            ai_service = get_ai_rag_service()
            print("[AI CHAT STREAM] Processing real-time stream with Claude...")

            async for event in ai_service.stream_message(
                message=input.message,
                session_id=user_id,
            ):
                if event.get("type") == "delta":
                    yield AiChatStreamChunk(
                        delta=event.get("delta", ""),
                        accumulated_text=event.get("accumulated_text", ""),
                        is_final=False,
                    )
                    continue

                if event.get("type") == "final":
                    product_ids = event.get("suggested_product_ids", [])
                    branch_ids = event.get("suggested_branch_ids", [])
                    accumulated_text = event.get("accumulated_text", "")

                    print("[AI CHAT STREAM] Sending final metadata chunk")
                    print(
                        f"[AI CHAT STREAM]   - Product IDs: {len(product_ids)}, Branch IDs: {len(branch_ids)}"
                    )
                    print(f"{'=' * 80}\n")

                    yield AiChatStreamChunk(
                        delta="",
                        accumulated_text=accumulated_text,
                        suggested_product_ids=product_ids,
                        suggested_branch_ids=branch_ids,
                        missing_fields=event.get("missing_fields", []),
                        confidence=event.get("confidence"),
                        is_final=True,
                    )

        except Exception as e:
            print(f"[AI CHAT STREAM] ERROR in streaming: {e}")
            import traceback

            traceback.print_exc()
            print(f"{'=' * 80}\n")

            # Determine error type
            error_message = str(e)
            if "Claude" in error_message or "Anthropic" in error_message or "API" in error_message:
                error_code = AiChatErrorCode.AI_SERVICE_ERROR
                user_message = "El servicio de IA no está disponible temporalmente. Intenta de nuevo en unos momentos."
            elif "timeout" in error_message.lower():
                error_code = AiChatErrorCode.AI_SERVICE_ERROR
                user_message = (
                    "La solicitud tardó demasiado. Por favor intenta de nuevo."
                )
            elif "database" in error_message.lower() or "mongo" in error_message.lower():
                error_code = AiChatErrorCode.AI_INTERNAL_ERROR
                user_message = "Error al procesar tu solicitud. Por favor intenta de nuevo."
            else:
                error_code = AiChatErrorCode.AI_INTERNAL_ERROR
                user_message = "Ocurrió un error inesperado. Por favor intenta de nuevo."

            yield AiChatStreamChunk(
                delta="",
                accumulated_text="",
                is_final=True,
                error=AiChatError(
                    code=error_code,
                    message=user_message,
                ),
            )
