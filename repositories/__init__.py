"""Repository instances for database operations."""
from .user_repository import UserRepository
from .business_repository import BusinessRepository
from .branch_repository import BranchRepository
from .product_repository import ProductRepository
from .category_repository import CategoryRepository
from .product_category_repository import ProductCategoryRepository
from .auth_repository import AuthRepository
from .payment_repository import PaymentRepository
from .payment_method_repository import PaymentMethodRepository
from .store_location_repository import StoreLocationRepository, store_locations_repo
from .business_type_repository import BusinessTypeRepository, business_type_repo
from .device_token_repository import DeviceTokenRepository, device_token_repo

# Repository instances
users_repo = UserRepository()
businesses_repo = BusinessRepository()
branches_repo = BranchRepository()
products_repo = ProductRepository()
categories_repo = CategoryRepository()
product_categories_repo = ProductCategoryRepository()
auth_repo = AuthRepository()
payments_repo = PaymentRepository()
payment_methods_repo = PaymentMethodRepository()

__all__ = [
    "UserRepository",
    "BusinessRepository",
    "BranchRepository",
    "ProductRepository",
    "CategoryRepository",
    "ProductCategoryRepository",
    "AuthRepository",
    "PaymentRepository",
    "PaymentMethodRepository",
    "StoreLocationRepository",
    "BusinessTypeRepository",
    "DeviceTokenRepository",
    "users_repo",
    "businesses_repo",
    "branches_repo",
    "products_repo",
    "categories_repo",
    "product_categories_repo",
    "auth_repo",
    "payments_repo",
    "payment_methods_repo",
    "store_locations_repo",
    "business_type_repo",
    "device_token_repo",
]
