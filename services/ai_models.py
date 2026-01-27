"""Pydantic models for AI structured outputs using Gemini SDK."""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


# ============================================================================
# Step 1: AI determines response type and generates search queries
# ============================================================================

class SearchQuery(BaseModel):
    """Search query for vector search."""
    collection: Literal["products", "branches", "businesses"] = Field(
        description="Collection to search in (products, branches, or businesses)"
    )
    query: str = Field(description="Search query text")
    limit: int = Field(default=10, description="Maximum number of results to return")


class AiIntentAnalysis(BaseModel):
    """
    AI's analysis of user intent and required actions.
    This is the FIRST response from AI to determine what to do.
    """
    response_type: Literal[
        "search_products",      # User wants to search/browse products
        "search_branches",      # User wants to find stores/branches
        "create_draft_order",   # User wants to create an order
        "request_details",      # AI needs more information
        "general_response"      # General conversation
    ] = Field(description="Type of response needed")

    reasoning: str = Field(description="Why this response type was chosen")

    search_queries: List[SearchQuery] = Field(
        default_factory=list,
        description="Vector search queries to execute (if needed)"
    )

    missing_info: List[str] = Field(
        default_factory=list,
        description="List of missing information needed (e.g., 'delivery_address', 'payment_method')"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this intent (0.0 to 1.0)"
    )


# ============================================================================
# Step 2: AI processes search results and creates final response
# ============================================================================

class ProductSuggestion(BaseModel):
    """Product suggested by AI."""
    product_id: str = Field(description="MongoDB ID of the suggested product")
    reason: str = Field(description="Why this product matches the user's query")


class BranchSuggestion(BaseModel):
    """Branch/store suggested by AI."""
    branch_id: str = Field(description="MongoDB ID of the suggested branch/store")
    reason: str = Field(description="Why this branch matches the user's query")


class DraftOrderData(BaseModel):
    """Data for creating a draft order."""
    branch_id: str = Field(description="Branch/store ID where order will be placed")
    business_id: str = Field(description="Business ID that owns the branch")
    product_ids: List[str] = Field(description="List of product IDs (must all be from same branch)")
    quantities: List[int] = Field(description="Corresponding quantities for each product in product_ids")
    delivery_address: Optional[str] = Field(default=None, description="Delivery street address")
    delivery_coordinates: Optional[List[float]] = Field(default=None, description="Delivery coordinates [longitude, latitude]")
    delivery_reference: Optional[str] = Field(default=None, description="Additional delivery reference or instructions")
    payment_method_id: Optional[str] = Field(default=None, description="Payment method ID chosen by user")
    special_instructions: Optional[str] = Field(default=None, description="Special instructions for the order")


class AiFinalResponse(BaseModel):
    """
    AI's final response after processing search results.
    This is the SECOND response from AI with actual data.
    """
    response_type: Literal[
        "search_products",
        "search_branches",
        "create_draft_order",
        "request_details",
        "general_response"
    ] = Field(description="Type of response: search_products, search_branches, create_draft_order, request_details, or general_response")

    ai_text: str = Field(description="Natural language response to show user")

    # For search responses
    suggested_products: List[ProductSuggestion] = Field(
        default_factory=list,
        description="Products suggested based on search results"
    )
    suggested_branches: List[BranchSuggestion] = Field(
        default_factory=list,
        description="Branches/stores suggested based on search results"
    )

    # For draft order creation
    draft_order: Optional[DraftOrderData] = Field(
        default=None,
        description="Draft order data if creating an order"
    )

    # For requesting details
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Fields needed from user (e.g., 'delivery_address', 'payment_method')"
    )

    # Metadata
    used_context: bool = Field(
        description="Whether conversation history was used to answer"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this response (0.0 to 1.0)"
    )


# ============================================================================
# Internal models for vector search results
# ============================================================================

class VectorSearchResult(BaseModel):
    """Result from vector search with metadata."""
    mongo_id: str
    score: float
    collection: str
    metadata: dict = Field(default_factory=dict)


class SearchContext(BaseModel):
    """Context assembled from vector searches."""
    products: List[dict] = Field(default_factory=list)
    branches: List[dict] = Field(default_factory=list)
    businesses: List[dict] = Field(default_factory=list)
