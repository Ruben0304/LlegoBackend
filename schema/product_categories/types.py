"""GraphQL type definitions for ProductCategory entity."""
import strawberry
from datetime import datetime


@strawberry.type
class ProductCategoryType:
    """Product category with icons for different platforms."""
    id: str
    branchType: str
    name: str
    iconIos: str
    iconWeb: str
    iconAndroid: str
    createdAt: datetime
