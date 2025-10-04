"""GraphQL schema configuration."""
import strawberry

from .users.queries import UserQuery
from .businesses.queries import BusinessQuery
from .branches.queries import BranchQuery
from .products.queries import ProductQuery
from .auth.mutations import AuthMutation


@strawberry.type
class Query(UserQuery, BusinessQuery, BranchQuery, ProductQuery):
    @strawberry.field(description="Saludo de ejemplo")
    def hello(self) -> str:
        return "Hola desde Llego Backend!"

    @strawberry.field(description="Saluda por nombre")
    def greet(self, name: str = "mundo") -> str:
        return f"Hola, {name}!"


@strawberry.type
class Mutation(AuthMutation):
    pass


# Create Strawberry GraphQL schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
