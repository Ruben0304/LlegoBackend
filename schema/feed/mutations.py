"""GraphQL mutation resolvers for Feed section ordering."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import feed_section_config_repo
from utils.graphql_auth import require_role

from .queries import FEED_SECTION_IDS
from .types import FeedSectionOrdenType


@strawberry.type
class FeedMutation:
    @strawberry.mutation(
        description=(
            "Fijar la posición de una sección del feed. "
            "orden=0 la pone arriba del todo; orden=null quita la posición fijada."
        )
    )
    async def set_feed_section_orden(
        self,
        info: Info,
        section_id: str,
        orden: Optional[int] = None,
        jwt: Optional[str] = None,
    ) -> FeedSectionOrdenType:
        require_role(jwt, info, ["admin", "manager"])

        if section_id not in FEED_SECTION_IDS:
            raise Exception(f"Sección no reconocida: {section_id}")

        if orden is None:
            await feed_section_config_repo.clear_orden(section_id)
        else:
            if orden < 0:
                raise Exception("El orden debe ser mayor o igual a 0")
            await feed_section_config_repo.set_orden(section_id, orden)

        return FeedSectionOrdenType(section_id=section_id, orden=orden)
