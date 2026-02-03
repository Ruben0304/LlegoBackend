"""GraphQL type definitions for BranchLike entity."""
import strawberry
from datetime import datetime


@strawberry.type
class BranchLikeType:
    id: str
    userId: str
    branchId: str
    createdAt: datetime
