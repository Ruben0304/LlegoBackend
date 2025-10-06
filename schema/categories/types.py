"""GraphQL type definitions for Category entity."""
import strawberry
from datetime import datetime
from typing import List


@strawberry.type
class SubcategoryType:
    name: str
    imageUrl: str


@strawberry.type
class CategoryType:
    id: str
    name: str
    imageUrl: str
    subcategories: List[SubcategoryType]
    createdAt: datetime
