"""GraphQL type definitions for AI Assistant entity."""
import strawberry
from typing import List, Union, Optional
from datetime import datetime
from schema.products.types import ProductType
from schema.branches.types import BranchType
from utils.s3 import generate_presigned_url


@strawberry.type
class ProductSuggestionType:
    """Product suggestion from AI with branch info for cards."""
    product: ProductType = strawberry.field(description="The suggested product")
    reason: str = strawberry.field(description="Why this product was suggested")
    
    # Branch info for product cards (denormalized for easy access)
    branch_name: Optional[str] = strawberry.field(description="Branch name where product is sold", default=None)
    branch_avatar: Optional[str] = strawberry.field(description="Branch avatar S3 key", default=None)
    branch_address: Optional[str] = strawberry.field(description="Branch address", default=None)
    branch_phone: Optional[str] = strawberry.field(description="Branch phone number", default=None)
    
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
    branch_avatar: Optional[str] = strawberry.field(description="Branch avatar URL", default=None)
    items: List[DraftOrderItemType] = strawberry.field(description="Order items")
    subtotal: float = strawberry.field(description="Subtotal amount")
    delivery_fee: float = strawberry.field(description="Delivery fee")
    total: float = strawberry.field(description="Total amount")
    currency: str = strawberry.field(description="Currency code")
    delivery_address: Optional[str] = strawberry.field(description="Delivery address", default=None)
    payment_method_id: Optional[str] = strawberry.field(description="Payment method ID", default=None)
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
        description="Products suggested by AI",
        default_factory=list
    )
    suggested_branches: List[BranchSuggestionType] = strawberry.field(
        description="Branches suggested by AI",
        default_factory=list
    )
    draft_order: Optional[DraftOrderType] = strawberry.field(
        description="Draft order created by AI (if applicable)",
        default=None
    )
    missing_fields: List[str] = strawberry.field(
        description="Fields that AI needs from user",
        default_factory=list
    )
    confidence: float = strawberry.field(description="AI confidence score (0.0 to 1.0)")


@strawberry.input
class AiAssistantChatInput:
    """Input for sending a message to the AI assistant."""
    message: str = strawberry.field(description="The user message/query to send")
    device_id: Optional[str] = strawberry.field(
        description="Unique device identifier from mobile app (required for free quota)",
        default=None
    )
