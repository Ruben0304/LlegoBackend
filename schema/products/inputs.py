"""GraphQL input types for Product mutations."""
import strawberry
from typing import Optional


@strawberry.input
class CreateProductInput:
    """Input for creating a product. Either branchId or businessId must be provided."""
    name: str
    description: str
    price: float
    image: str  # Path from /upload/product/image endpoint
    branchId: Optional[str] = None  # Optional if businessId is provided
    businessId: Optional[str] = None  # Optional if branchId is provided
    currency: str = "USD"
    weight: Optional[str] = None
    categoryId: Optional[str] = None
    variantListIds: Optional[list[str]] = None  # IDs de listas de variantes a asignar


@strawberry.input
class UpdateProductInput:
    """Input for updating a product."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    weight: Optional[str] = None
    availability: Optional[bool] = None
    categoryId: Optional[str] = None
    image: Optional[str] = None  # New image path from /upload/product/image
    variantListIds: Optional[list[str]] = None  # IDs de listas de variantes a asignar
