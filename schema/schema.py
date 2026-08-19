"""GraphQL schema configuration."""

from typing import Optional

import strawberry
from strawberry.types import Info

from utils.graphql_auth import apply_optional_jwt

from .ads.mutations import AdCampaignMutation
from .ads.queries import AdCampaignQuery
from .ai_assistant.queries import AiAssistantQuery
from .ai_assistant.subscriptions import AiAssistantSubscription
from .app_config.mutations import AppConfigMutations
from .app_config.queries import AppConfigQueries
from .auth.mutations import AuthMutation
from .branch_likes.mutations import BranchLikesMutation
from .branches.mutations import BranchMutation
from .branches.queries import BranchQuery
from .business_types.mutations import BusinessTypeMutation
from .business_types.queries import BusinessTypeQuery
from .businesses.mutations import BusinessMutation
from .businesses.queries import BusinessQuery
from .categories.queries import CategoryQuery
from .combos.mutations import ComboMutation
from .combos.queries import ComboQuery
from .extensions import ErrorLoggingExtension, LastSeenExtension, UserIdExtension
from .favorites_cart.mutations import FavoritesCartMutation
from .feed.mutations import FeedMutation
from .feed.queries import FeedQuery
from .feedbacks.mutations import FeedbackMutation
from .feedbacks.queries import FeedbackQuery
from .invitations.mutations import InvitationMutation
from .invitations.queries import InvitationQuery
from .orders.mutations import OrderMutation
from .orders.queries import OrderQuery
from .orders.subscriptions import OrderSubscription
from .payments.mutations import PaymentMutation
from .payments.queries import PaymentMethodQuery
from .product_categories.queries import ProductCategoryQuery
from .products.mutations import ProductMutation
from .products.queries import ProductQuery
from .promos.mutations import PromoMutation
from .promos.queries import PromoQuery
from .promotional_videos.mutations import PromotionalVideoMutation
from .promotional_videos.queries import PromotionalVideoQuery
from .searches.mutations import SearchesMutation
from .showcases.mutations import ShowcaseMutation
from .showcases.queries import ShowcaseQuery
from .shortcut_transfers.queries import ShortcutTransferQuery
from .surveys.mutations import SurveyMutation
from .surveys.queries import SurveyQuery
from .sync.queries import SyncQuery
from .tutorials.mutations import TutorialMutation
from .tutorials.queries import TutorialQuery
from .users.mutations import UserMutation
from .users.queries import UserQuery
from .variant_lists.mutations import VariantListMutation
from .variant_lists.queries import VariantListQuery
from .wallet.mutations import WalletMutation
from .wallet.queries import WalletQuery


@strawberry.type
class Query(
    UserQuery,
    BusinessQuery,
    BranchQuery,
    ProductQuery,
    ShowcaseQuery,
    CategoryQuery,
    ProductCategoryQuery,
    ComboQuery,
    AiAssistantQuery,
    OrderQuery,
    BusinessTypeQuery,
    PaymentMethodQuery,
    WalletQuery,
    InvitationQuery,
    AppConfigQueries,
    FeedbackQuery,
    SurveyQuery,
    FeedQuery,
    TutorialQuery,
    PromotionalVideoQuery,
    ShortcutTransferQuery,
    VariantListQuery,
    SyncQuery,
    AdCampaignQuery,
    PromoQuery,
):
    @strawberry.field(description="Saludo de ejemplo")
    def hello(self, info: Info, jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return "Hola desde Llego Backend!"

    @strawberry.field(description="Saluda por nombre")
    def greet(self, info: Info, name: str = "mundo", jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return f"Hola, {name}!"


@strawberry.type
class Mutation(
    AuthMutation,
    UserMutation,
    BusinessMutation,
    BranchMutation,
    ProductMutation,
    ShowcaseMutation,
    ComboMutation,
    OrderMutation,
    BusinessTypeMutation,
    PaymentMutation,
    WalletMutation,
    InvitationMutation,
    AppConfigMutations,
    FeedbackMutation,
    SurveyMutation,
    FavoritesCartMutation,
    SearchesMutation,
    BranchLikesMutation,
    TutorialMutation,
    PromotionalVideoMutation,
    VariantListMutation,
    AdCampaignMutation,
    FeedMutation,
    PromoMutation,
):
    pass


@strawberry.type
class Subscription(OrderSubscription, AiAssistantSubscription):
    pass


# Create Strawberry GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    extensions=[UserIdExtension, ErrorLoggingExtension, LastSeenExtension],
)
