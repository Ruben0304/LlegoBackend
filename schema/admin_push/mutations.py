"""GraphQL mutations for push notifications sent from the Panel Admin."""

import strawberry
from strawberry.types import Info

from services.admin_push import send_admin_push
from utils.graphql_auth import require_role

from .types import (
    AdminPushNotificationType,
    AdminSendPushInput,
    notification_to_type,
    recipients_to_domain,
)


@strawberry.type
class AdminPushMutation:
    @strawberry.mutation(
        description=(
            "(Admin) Envía una notificación push a cuentas, dispositivos concretos "
            "o a toda una app, y la guarda en el historial"
        )
    )
    async def admin_send_push(
        self, info: Info, input: AdminSendPushInput, jwt: str
    ) -> AdminPushNotificationType:
        # Solo admin: un envío a toda una app llega a todos sus usuarios.
        admin_id = require_role(jwt, info, ["admin"])
        try:
            notification = await send_admin_push(
                title=input.title,
                body=input.body,
                sent_by_id=admin_id,
                **recipients_to_domain(input.recipients),
            )
        except ValueError as e:
            raise Exception(str(e))
        return notification_to_type(notification)
