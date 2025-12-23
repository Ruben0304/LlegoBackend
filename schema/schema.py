"""GraphQL schema configuration."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .users.queries import UserQuery
from .businesses.queries import BusinessQuery
from .branches.queries import BranchQuery
from .products.queries import ProductQuery
from .categories.queries import CategoryQuery
from .auth.mutations import AuthMutation
from .ai_assistant.queries import AiAssistantQuery
from .extensions import UserIdExtension
from utils.graphql_auth import apply_optional_jwt


@strawberry.type
class Query(UserQuery, BusinessQuery, BranchQuery, ProductQuery, CategoryQuery, AiAssistantQuery):
    @strawberry.field(description="Saludo de ejemplo")
    def hello(self, info: Info, jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return "Hola desde Llego Backend!"

    @strawberry.field(description="Saluda por nombre")
    def greet(self, info: Info, name: str = "mundo", jwt: Optional[str] = None) -> str:
        apply_optional_jwt(jwt, info)
        return f"Hola, {name}!"


@strawberry.type
class Mutation(AuthMutation):
    pass


# Create Strawberry GraphQL schema
schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=[UserIdExtension])
