"""Repository instances for database operations."""
from .user_repository import UserRepository
from .business_repository import BusinessRepository
from .branch_repository import BranchRepository
from .product_repository import ProductRepository
from .auth_repository import AuthRepository

# Repository instances
users_repo = UserRepository()
businesses_repo = BusinessRepository()
branches_repo = BranchRepository()
products_repo = ProductRepository()
auth_repo = AuthRepository()

__all__ = [
    "UserRepository",
    "BusinessRepository",
    "BranchRepository",
    "ProductRepository",
    "AuthRepository",
    "users_repo",
    "businesses_repo",
    "branches_repo",
    "products_repo",
    "auth_repo",
]
