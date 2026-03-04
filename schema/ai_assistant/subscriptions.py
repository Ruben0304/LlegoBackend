"""GraphQL subscription resolvers for AI Assistant streaming."""

import asyncio
import re
from typing import AsyncGenerator, Optional

import strawberry
from strawberry.types import Info

from repositories import branches_repo, draft_orders_repo, products_repo
from schema.branches.utils import branch_to_dict
from schema.branches.types import BranchType
from schema.products.types import ProductType
from services.ai_quota_service import ai_quota_service
from services.ai_rag_service import AiRagService
from utils.graphql_auth import require_auth
from utils.rate_limit import rate_limit_graphql
from utils.serialization import to_strawberry_dict

from .types import (
    AiAssistantChatInput,
    AiChatError,
    AiChatErrorCode,
    AiChatQuotaInfo,
    AiChatStreamChunk,
    BranchSuggestionType,
    DraftOrderItemType,
    DraftOrderType,
    ProductSuggestionType,
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
        the response, followed by structured data (products, branches) in the final chunk.
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

            # Initialize AI RAG service
            ai_service = AiRagService()

            # Process message with RAG (non-streaming for now)
            # In the future, this could be enhanced to stream from the LLM
            print(f"[AI CHAT STREAM] Processing message with RAG...")
            response = await ai_service.send_message(
                message=input.message,
                session_id=user_id,
            )

            print(f"[AI CHAT STREAM] Response received from AI service")
            print(f"[AI CHAT STREAM]   - response_type: {response.response_type}")
            print(f"[AI CHAT STREAM]   - ai_text length: {len(response.ai_text)} chars")

            # Simulate streaming by chunking the text
            # Split text into words for streaming
            words = response.ai_text.split()
            accumulated_text = ""
            chunk_size = 3  # Send 3 words at a time

            print(
                f"[AI CHAT STREAM] Streaming {len(words)} words in chunks of {chunk_size}..."
            )

            for i in range(0, len(words), chunk_size):
                chunk_words = words[i : i + chunk_size]
                delta = " ".join(chunk_words)
                if accumulated_text:
                    delta = " " + delta
                accumulated_text += delta

                yield AiChatStreamChunk(
                    delta=delta,
                    accumulated_text=accumulated_text,
                    is_final=False,
                )

                # Small delay to simulate streaming
                await asyncio.sleep(0.1)

            # Convert suggested products to GraphQL types
            suggested_products = []
            print(
                f"[AI CHAT STREAM] Converting {len(response.suggested_products)} product suggestions..."
            )

            # Pre-fetch all branches needed for products
            product_ids = [s.product_id for s in response.suggested_products]
            products_data = await products_repo.get_by_ids(product_ids)
            products_map = {p.id: p for p in products_data}

            # Get unique branch IDs from products
            branch_ids = list(set([p.branchId for p in products_data]))
            branches_map = {}
            if branch_ids:
                branches_data = await branches_repo.get_by_ids(branch_ids)
                branches_map = {b.id: b for b in branches_data}

            for suggestion in response.suggested_products:
                product = products_map.get(suggestion.product_id)
                if product:
                    branch = branches_map.get(product.branchId)
                    suggested_products.append(
                        ProductSuggestionType(
                            product=ProductType(**to_strawberry_dict(product)),
                            reason=suggestion.reason,
                            branch_name=branch.name if branch else None,
                            branch_avatar=branch.avatar if branch else None,
                            branch_address=branch.address if branch else None,
                            branch_phone=branch.phone if branch else None,
                        )
                    )

            # Convert suggested branches to GraphQL types
            suggested_branches = []
            print(
                f"[AI CHAT STREAM] Converting {len(response.suggested_branches)} branch suggestions..."
            )
            for suggestion in response.suggested_branches:
                branch = await branches_repo.get_by_id(suggestion.branch_id)
                if branch:
                    branch_type = BranchType(**branch_to_dict(branch))
                    suggested_branches.append(
                        BranchSuggestionType(
                            branch=branch_type, reason=suggestion.reason
                        )
                    )

            # Convert draft order if present
            draft_order = None
            if response.draft_order:
                print(
                    f"[AI CHAT STREAM] Draft order creation detected, fetching from database..."
                )
                drafts = await draft_orders_repo.get_pending_by_session(user_id)
                if drafts:
                    latest_draft = drafts[0]
                    draft_order = DraftOrderType(
                        id=latest_draft.id,
                        session_id=latest_draft.sessionId,
                        customer_id=latest_draft.customerId,
                        branch_id=latest_draft.branchId,
                        business_id=latest_draft.businessId,
                        branch_avatar=latest_draft.branchAvatar,
                        items=[
                            DraftOrderItemType(
                                product_id=item.productId,
                                name=item.name,
                                price=item.price,
                                quantity=item.quantity,
                                image_url=item.imageUrl,
                            )
                            for item in latest_draft.items
                        ],
                        subtotal=latest_draft.subtotal,
                        delivery_fee=latest_draft.deliveryFee,
                        total=latest_draft.total,
                        currency=latest_draft.currency,
                        delivery_address=str(latest_draft.deliveryAddress)
                        if latest_draft.deliveryAddress
                        else None,
                        payment_method_id=latest_draft.paymentMethodId,
                        status=latest_draft.status,
                        created_at=latest_draft.createdAt,
                        expires_at=latest_draft.expiresAt,
                    )

            # Send final chunk with all structured data
            print(f"[AI CHAT STREAM] Sending final chunk with structured data")
            print(
                f"[AI CHAT STREAM]   - Products: {len(suggested_products)}, Branches: {len(suggested_branches)}"
            )
            print(f"{'=' * 80}\n")

            yield AiChatStreamChunk(
                delta="",
                accumulated_text=accumulated_text,
                suggested_products=suggested_products,
                suggested_branches=suggested_branches,
                draft_order=draft_order,
                missing_fields=response.missing_fields,
                confidence=response.confidence,
                is_final=True,
            )

        except Exception as e:
            print(f"[AI CHAT STREAM] ERROR in streaming: {e}")
            import traceback

            traceback.print_exc()
            print(f"{'=' * 80}\n")

            # Determine error type
            error_message = str(e)
            if "DeepSeek" in error_message or "API" in error_message:
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
