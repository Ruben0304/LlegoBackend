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
from .error_log_repository import ErrorLogRepository, error_log_repo
from .wallet_repository import WalletTransactionRepository
from .branch_invitation_repository import BranchInvitationRepository, branch_invitations_repo
from .business_access_repository import BusinessAccessRepository, business_access_repo
from .app_config_repository import AppConfigRepository, BusinessAppConfigRepository
from .feedback_repository import FeedbackRepository
from .survey_repository import SurveyRepository
from .survey_response_repository import SurveyResponseRepository
from .favorites_cart_repository import FavoritesCartRepository
from .searches_repository import SearchesRepository
from .chat_memory_repository import ChatMemoryRepository
from .draft_order_repository import DraftOrderRepository
from .branch_likes_repository import BranchLikesRepository

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
wallet_transactions_repo = WalletTransactionRepository()
app_config_repo = AppConfigRepository()
business_app_config_repo = BusinessAppConfigRepository()
feedbacks_repo = FeedbackRepository()
surveys_repo = SurveyRepository()
survey_responses_repo = SurveyResponseRepository()
favorites_cart_repo = FavoritesCartRepository()
searches_repo = SearchesRepository()
chat_memory_repo = ChatMemoryRepository()
draft_orders_repo = DraftOrderRepository()
branch_likes_repo = BranchLikesRepository()

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
    "WalletTransactionRepository",
    "BranchInvitationRepository",
    "BusinessAccessRepository",
    "AppConfigRepository",
    "BusinessAppConfigRepository",
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
    "ErrorLogRepository",
    "error_log_repo",
    "wallet_transactions_repo",
    "branch_invitations_repo",
    "business_access_repo",
    "app_config_repo",
    "business_app_config_repo",
    "FeedbackRepository",
    "SurveyRepository",
    "SurveyResponseRepository",
    "FavoritesCartRepository",
    "SearchesRepository",
    "ChatMemoryRepository",
    "DraftOrderRepository",
    "BranchLikesRepository",
    "feedbacks_repo",
    "surveys_repo",
    "survey_responses_repo",
    "favorites_cart_repo",
    "searches_repo",
    "chat_memory_repo",
    "draft_orders_repo",
    "branch_likes_repo",
]
