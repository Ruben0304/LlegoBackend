"""GraphQL schema configuration."""
import strawberry

from .users.queries import UserQuery
from .businesses.queries import BusinessQuery
from .branches.queries import BranchQuery
from .products.queries import ProductQuery
from .categories.queries import CategoryQuery
from .auth.mutations import AuthMutation
from .payments.mutations import PaymentMutation


@strawberry.type
class Query(UserQuery, BusinessQuery, BranchQuery, ProductQuery, CategoryQuery):
    @strawberry.field(description="Saludo de ejemplo")
    def hello(self) -> str:
        return "Hola desde Llego Backend!"

    @strawberry.field(description="Saluda por nombre")
    def greet(self, name: str = "mundo") -> str:
        return f"Hola, {name}!"


@strawberry.type
class Mutation(AuthMutation, PaymentMutation):
    pass


# Create Strawberry GraphQL schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
