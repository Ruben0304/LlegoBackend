"""GraphQL schema configuration."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .users.queries import UserQuery
from .users.mutations import UserMutation
from .businesses.queries import BusinessQuery
from .branches.queries import BranchQuery
from .products.queries import ProductQuery
from .categories.queries import CategoryQuery
from .auth.mutations import AuthMutation
from .businesses.mutations import BusinessMutation
from .branches.mutations import BranchMutation
from .products.mutations import ProductMutation
from .ai_assistant.queries import AiAssistantQuery
from .orders.queries import OrderQuery
from .orders.mutations import OrderMutation
from .orders.subscriptions import OrderSubscription
from .extensions import UserIdExtension
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class Query(UserQuery, BusinessQuery, BranchQuery, ProductQuery, CategoryQuery, AiAssistantQuery, OrderQuery):
    @strawberry.field(description="Saludo de ejemplo")
    def hello(self, info: Info, jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return "Hola desde Llego Backend!"

    @strawberry.field(description="Saluda por nombre")
    def greet(self, info: Info, name: str = "mundo", jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return f"Hola, {name}!"


@strawberry.type
class Mutation(AuthMutation, UserMutation, BusinessMutation, BranchMutation, ProductMutation, OrderMutation):
    pass


@strawberry.type
class Subscription(OrderSubscription):
    pass


# Create Strawberry GraphQL schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    extensions=[UserIdExtension]
)
