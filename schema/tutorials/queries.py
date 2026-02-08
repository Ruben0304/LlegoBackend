"""GraphQL query resolvers for Tutorial entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import TutorialType, AppTarget
from domain.models import tutorials_repo
from utils.rate_limit import rate_limit_graphql


@strawberry.type
class TutorialQuery:
    @strawberry.field(description="Get all tutorials")
    async def tutorials(self, info: Info) -> List[TutorialType]:
        """Get all tutorials ordered by order field."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_all()
        return [TutorialType(**tutorial.model_dump()) for tutorial in tutorials]

    @strawberry.field(description="Get active tutorials only")
    async def active_tutorials(self, info: Info) -> List[TutorialType]:
        """Get all active tutorials ordered by order field."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_active()
        return [TutorialType(**tutorial.model_dump()) for tutorial in tutorials]

    @strawberry.field(description="Get tutorials by app target")
    async def tutorials_by_app(
        self,
        info: Info,
        appTarget: AppTarget
    ) -> List[TutorialType]:
        """Get tutorials filtered by app target (includes 'both' tutorials)."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_by_app_target(appTarget.value)
        return [TutorialType(**tutorial.model_dump()) for tutorial in tutorials]

    @strawberry.field(description="Get tutorial by ID")
    async def tutorial(
        self,
        info: Info,
        id: str
    ) -> Optional[TutorialType]:
        """Get a single tutorial by ID."""
        rate_limit_graphql(info, "graphql")
        tutorial = await tutorials_repo.get_by_id(id)
        if tutorial:
            return TutorialType(**tutorial.model_dump())
        return None

    @strawberry.field(description="Search tutorials by title, description or tags")
    async def search_tutorials(
        self,
        info: Info,
        query: str
    ) -> List[TutorialType]:
        """Search tutorials by title, description or tags."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.search(query)
        return [TutorialType(**tutorial.model_dump()) for tutorial in tutorials]

    @strawberry.field(description="Get tutorials by tags")
    async def tutorials_by_tags(
        self,
        info: Info,
        tags: List[str]
    ) -> List[TutorialType]:
        """Get tutorials that have any of the provided tags."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_by_tags(tags)
        return [TutorialType(**tutorial.model_dump()) for tutorial in tutorials]
