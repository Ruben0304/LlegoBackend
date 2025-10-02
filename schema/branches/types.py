"""GraphQL type definitions for Branch entity."""
import strawberry
from typing import List
from datetime import datetime


@strawberry.type
class CoordinatesType:
    type: str
    coordinates: List[float]


@strawberry.type
class BranchType:
    id: str
    businessId: str
    name: str
    address: str
    coordinates: CoordinatesType
    phone: str
    schedule: strawberry.scalars.JSON
    managerIds: List[str]
    status: str
    createdAt: datetime
