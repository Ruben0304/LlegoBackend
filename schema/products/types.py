"""GraphQL type definitions for Product entity."""
import strawberry
from datetime import datetime
from typing import Optional


@strawberry.type
class ProductType:
    id: str
    branchId: str
    name: str
    description: str
    weight: str
    price: float
    currency: str
    image: str
    availability: bool
    categoryId: Optional[str] = None
    createdAt: datetime
