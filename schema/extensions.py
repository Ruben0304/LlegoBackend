"""GraphQL schema extensions."""
from strawberry.extensions import SchemaExtension


class UserIdExtension(SchemaExtension):
    """Attach user_id to GraphQL response extensions when present."""

    def on_request_end(self) -> None:
        context = self.execution_context.context
        if not isinstance(context, dict):
            return

        user_id = context.get("user_id")
        if not user_id or not self.execution_context.result:
            return

        result = self.execution_context.result
        if result.extensions is None:
            result.extensions = {}
        result.extensions["user_id"] = user_id
