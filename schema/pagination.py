"""Cursor-based pagination types for GraphQL (Relay-style)."""
import strawberry
from typing import Generic, TypeVar, List, Optional
import base64

T = TypeVar("T")


def encode_cursor(value: str) -> str:
    """Encode a value into a cursor string."""
    return base64.urlsafe_b64encode(f"cursor:{value}".encode()).decode()


def decode_cursor(cursor: str) -> str:
    """Decode a cursor string back to its original value."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        return decoded.replace("cursor:", "")
    except Exception:
        return ""


def encode_scored_cursor(score: float, id: str) -> str:
    """Encode score and ID into a cursor for scored results."""
    return base64.urlsafe_b64encode(f"scored:{score}:{id}".encode()).decode()


def decode_scored_cursor(cursor: str) -> tuple[Optional[float], Optional[str]]:
    """Decode a scored cursor back to score and ID."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        parts = decoded.replace("scored:", "").split(":", 1)
        if len(parts) == 2:
            return float(parts[0]), parts[1]
    except Exception:
        pass
    return None, None


@strawberry.type
class PageInfo:
    """Pagination metadata."""
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str] = None
    end_cursor: Optional[str] = None
    total_count: int = 0


@strawberry.type
class ProductEdge:
    """Edge wrapper for Product in connection."""
    node: "ScoredProductType"
    cursor: str


@strawberry.type
class ProductConnection:
    """Relay-style connection for paginated products."""
    edges: List[ProductEdge]
    page_info: PageInfo


@strawberry.type
class BranchEdge:
    """Edge wrapper for Branch in connection."""
    node: "ScoredBranchType"
    cursor: str


@strawberry.type
class BranchConnection:
    """Relay-style connection for paginated branches."""
    edges: List[BranchEdge]
    page_info: PageInfo


@strawberry.type
class NearbyBranchEdge:
    """Edge wrapper for NearbyBranch in connection."""
    node: "NearbyBranchType"
    cursor: str


@strawberry.type
class NearbyBranchConnection:
    """Relay-style connection for paginated nearby branches."""
    edges: List[NearbyBranchEdge]
    page_info: PageInfo


# Import types for forward references
from schema.products.types import ScoredProductType
from schema.branches.types import ScoredBranchType, NearbyBranchType
