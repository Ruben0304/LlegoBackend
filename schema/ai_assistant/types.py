"""GraphQL type definitions for AI Assistant entity."""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

import strawberry

from schema.branches.types import BranchType
from schema.businesses.types import BusinessType
from schema.products.types import ProductType
from utils.s3 import generate_presigned_url

# ============================================================================
# Semantic Search types
# ============================================================================


@strawberry.enum
class SemanticSearchCollection(Enum):
    """Collections available for semantic search."""

    PRODUCTS = "products"
    BRANCHES = "branches"
    BUSINESSES = "businesses"


@strawberry.type
class SemanticSearchProductResult:
    """A product result from semantic vector search."""

    score: float = strawberry.field(
        description="Similarity score from vector search (0.0 to 1.0)"
    )
    product: ProductType = strawberry.field(description="The matched product")
    branch_name: Optional[str] = strawberry.field(
        description="Branch name where product is sold", default=None
    )
    branch_avatar: Optional[str] = strawberry.field(
        description="Branch avatar S3 key", default=None
    )
    branch_address: Optional[str] = strawberry.field(
        description="Branch address", default=None
    )
    branch_phone: Optional[str] = strawberry.field(
        description="Branch phone number", default=None
    )

    @strawberry.field(description="Presigned URL for the branch avatar")
    def branch_avatar_url(self) -> Optional[str]:
        if self.branch_avatar:
            return generate_presigned_url(self.branch_avatar)
        return None


@strawberry.type
class SemanticSearchBranchResult:
    """A branch result from semantic vector search."""

    score: float = strawberry.field(
        description="Similarity score from vector search (0.0 to 1.0)"
    )
    branch: BranchType = strawberry.field(description="The matched branch")


@strawberry.type
class SemanticSearchBusinessResult:
    """A business result from semantic vector search."""

    score: float = strawberry.field(
        description="Similarity score from vector search (0.0 to 1.0)"
    )
    business: BusinessType = strawberry.field(description="The matched business")


@strawberry.type
class SemanticSearchResultType:
    """Combined result from semantic vector search across collections."""

    collection: str = strawberry.field(
        description="Collection that was searched: products, branches, or businesses"
    )
    total_results: int = strawberry.field(
        description="Total number of results returned"
    )
    products: List[SemanticSearchProductResult] = strawberry.field(
        description="Product results (populated when collection=products)",
        default_factory=list,
    )
    branches: List[SemanticSearchBranchResult] = strawberry.field(
        description="Branch results (populated when collection=branches)",
        default_factory=list,
    )
    businesses: List[SemanticSearchBusinessResult] = strawberry.field(
        description="Business results (populated when collection=businesses)",
        default_factory=list,
    )


@strawberry.type
class ProductSuggestionType:
    """Product suggestion from AI with branch info for cards."""

    product: ProductType = strawberry.field(description="The suggested product")
    reason: str = strawberry.field(description="Why this product was suggested")

    # Branch info for product cards (denormalized for easy access)
    branch_name: Optional[str] = strawberry.field(
        description="Branch name where product is sold", default=None
    )
    branch_avatar: Optional[str] = strawberry.field(
        description="Branch avatar S3 key", default=None
    )
    branch_address: Optional[str] = strawberry.field(
        description="Branch address", default=None
    )
    branch_phone: Optional[str] = strawberry.field(
        description="Branch phone number", default=None
    )

    @strawberry.field(description="Presigned URL for the branch avatar")
    def branch_avatar_url(self) -> Optional[str]:
        if self.branch_avatar:
            return generate_presigned_url(self.branch_avatar)
        return None


@strawberry.type
class BranchSuggestionType:
    """Branch/store suggestion from AI."""

    branch: BranchType = strawberry.field(description="The suggested branch")
    reason: str = strawberry.field(description="Why this branch was suggested")


@strawberry.type
class DraftOrderItemType:
    """Item in a draft order."""

    product_id: str = strawberry.field(description="Product ID")
    name: str = strawberry.field(description="Product name")
    price: float = strawberry.field(description="Product price")
    quantity: int = strawberry.field(description="Quantity")
    image_url: str = strawberry.field(description="Product image URL")


@strawberry.type
class DraftOrderType:
    """Draft order created by AI assistant."""

    id: str = strawberry.field(description="Draft order ID")
    session_id: str = strawberry.field(description="Session ID (user ID)")
    customer_id: str = strawberry.field(description="Customer ID")
    branch_id: str = strawberry.field(description="Branch ID")
    business_id: str = strawberry.field(description="Business ID")
    branch_avatar: Optional[str] = strawberry.field(
        description="Branch avatar URL", default=None
    )
    items: List[DraftOrderItemType] = strawberry.field(description="Order items")
    subtotal: float = strawberry.field(description="Subtotal amount")
    delivery_fee: float = strawberry.field(description="Delivery fee")
    total: float = strawberry.field(description="Total amount")
    currency: str = strawberry.field(description="Currency code")
    delivery_address: Optional[str] = strawberry.field(
        description="Delivery address", default=None
    )
    payment_method_id: Optional[str] = strawberry.field(
        description="Payment method ID", default=None
    )
    status: str = strawberry.field(description="Draft status")
    created_at: datetime = strawberry.field(description="Creation timestamp")
    expires_at: datetime = strawberry.field(description="Expiration timestamp")


@strawberry.type
class AiAssistantResponseType:
    """Complete AI Assistant response with RAG."""

    response_type: str = strawberry.field(
        description="Type of response: search_products, search_branches, create_draft_order, request_details, general_response"
    )
    ai_text: str = strawberry.field(description="Natural language response from AI")
    suggested_products: List[ProductSuggestionType] = strawberry.field(
        description="Products suggested by AI", default_factory=list
    )
    suggested_branches: List[BranchSuggestionType] = strawberry.field(
        description="Branches suggested by AI", default_factory=list
    )
    draft_order: Optional[DraftOrderType] = strawberry.field(
        description="Draft order created by AI (if applicable)", default=None
    )
    missing_fields: List[str] = strawberry.field(
        description="Fields that AI needs from user", default_factory=list
    )
    confidence: float = strawberry.field(description="AI confidence score (0.0 to 1.0)")


@strawberry.input
class AiAssistantChatInput:
    """Input for sending a message to the AI assistant."""

    message: str = strawberry.field(description="The user message/query to send")
    device_id: Optional[str] = strawberry.field(
        description="Unique device identifier from mobile app (required for free quota)",
        default=None,
    )
    stream: bool = strawberry.field(
        description="Enable streaming mode (requires GraphQL subscription)",
        default=False,
    )


# ============================================================================
# Error handling types
# ============================================================================


@strawberry.enum
class AiChatErrorCode(Enum):
    """Error codes for AI chat."""

    AI_MESSAGE_TOO_LONG = "AI_MESSAGE_TOO_LONG"
    AI_DEVICE_ID_REQUIRED = "AI_DEVICE_ID_REQUIRED"
    AI_DAILY_DEVICE_QUOTA_EXCEEDED = "AI_DAILY_DEVICE_QUOTA_EXCEEDED"
    AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"
    AI_FREE_QUOTA_EXCEEDED = "AI_FREE_QUOTA_EXCEEDED"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    AI_RATE_LIMIT_EXCEEDED = "AI_RATE_LIMIT_EXCEEDED"
    AI_INVALID_REQUEST = "AI_INVALID_REQUEST"
    AI_INTERNAL_ERROR = "AI_INTERNAL_ERROR"


@strawberry.type
class AiChatQuotaInfo:
    """Quota information for AI chat."""

    source: str = strawberry.field(description="Quota source identifier")
    limit: int = strawberry.field(description="Total quota limit")
    used: int = strawberry.field(description="Amount used")
    remaining: int = strawberry.field(description="Amount remaining")


@strawberry.type
class AiChatError:
    """Error type for AI chat operations."""

    code: AiChatErrorCode = strawberry.field(description="Error code")
    message: str = strawberry.field(description="Human-readable error message")
    quota: Optional[AiChatQuotaInfo] = strawberry.field(
        description="Quota information (if applicable)", default=None
    )
    retry_after: Optional[int] = strawberry.field(
        description="Seconds until retry is allowed (if applicable)", default=None
    )
    max_words: Optional[int] = strawberry.field(
        description="Maximum allowed words (for MESSAGE_TOO_LONG)", default=None
    )
    words_count: Optional[int] = strawberry.field(
        description="Actual word count (for MESSAGE_TOO_LONG)", default=None
    )


@strawberry.type
class AiChatResult:
    """Result type for AI chat with error handling."""

    success: Optional[AiAssistantResponseType] = strawberry.field(
        description="Successful response data", default=None
    )
    error: Optional[AiChatError] = strawberry.field(
        description="Error information if request failed", default=None
    )


# ============================================================================
# Streaming types
# ============================================================================


@strawberry.type
class AiChatStreamChunk:
    """A chunk of the streaming AI chat response."""

    delta: str = strawberry.field(
        description="Incremental text delta for this chunk"
    )
    accumulated_text: str = strawberry.field(
        description="Full accumulated text so far"
    )
    suggested_products: List[ProductSuggestionType] = strawberry.field(
        description="Products suggested (sent in final chunk)", default_factory=list
    )
    suggested_branches: List[BranchSuggestionType] = strawberry.field(
        description="Branches suggested (sent in final chunk)", default_factory=list
    )
    suggested_product_ids: List[str] = strawberry.field(
        description="Product IDs suggested (sent in final chunk)", default_factory=list
    )
    suggested_branch_ids: List[str] = strawberry.field(
        description="Branch IDs suggested (sent in final chunk)", default_factory=list
    )
    draft_order: Optional[DraftOrderType] = strawberry.field(
        description="Draft order (sent in final chunk)", default=None
    )
    missing_fields: List[str] = strawberry.field(
        description="Missing fields (sent in final chunk)", default_factory=list
    )
    confidence: Optional[float] = strawberry.field(
        description="Confidence score (sent in final chunk)", default=None
    )
    is_final: bool = strawberry.field(
        description="Whether this is the final chunk"
    )
    error: Optional[AiChatError] = strawberry.field(
        description="Error if streaming failed", default=None
    )
