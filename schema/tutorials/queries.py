"""GraphQL query resolvers for Tutorial entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import tutorials_repo
from utils.rate_limit import rate_limit_graphql
from utils.serialization import to_strawberry_dict

from .types import AppTarget, TutorialType


@strawberry.type
class TutorialQuery:
    @strawberry.field(description="Get all tutorials")
    async def tutorials(self, info: Info) -> List[TutorialType]:
        """Get all tutorials ordered by order field."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_all()
        return [
            TutorialType(**to_strawberry_dict(tutorial)) for tutorial in tutorials
        ]

    @strawberry.field(description="Get active tutorials only")
    async def active_tutorials(self, info: Info) -> List[TutorialType]:
        """Get all active tutorials ordered by order field."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_active()
        return [
            TutorialType(**to_strawberry_dict(tutorial)) for tutorial in tutorials
        ]

    @strawberry.field(description="Get tutorials by app target")
    async def tutorials_by_app(
        self, info: Info, appTarget: AppTarget
    ) -> List[TutorialType]:
        """Get tutorials filtered by app target (includes 'both' tutorials)."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_by_app_target(appTarget.value)
        return [
            TutorialType(**to_strawberry_dict(tutorial)) for tutorial in tutorials
        ]

    @strawberry.field(description="Get tutorial by ID")
    async def tutorial(self, info: Info, id: str) -> Optional[TutorialType]:
        """Get a single tutorial by ID."""
        rate_limit_graphql(info, "graphql")
        tutorial = await tutorials_repo.get_by_id(id)
        if tutorial:
            return TutorialType(**to_strawberry_dict(tutorial))
        return None

    @strawberry.field(description="Search tutorials by title, description or tags")
    async def search_tutorials(self, info: Info, query: str) -> List[TutorialType]:
        """Search tutorials by title, description or tags."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.search(query)
        return [
            TutorialType(**to_strawberry_dict(tutorial)) for tutorial in tutorials
        ]

    @strawberry.field(description="Get tutorials by tags")
    async def tutorials_by_tags(
        self, info: Info, tags: List[str]
    ) -> List[TutorialType]:
        """Get tutorials that have any of the provided tags."""
        rate_limit_graphql(info, "graphql")
        tutorials = await tutorials_repo.get_by_tags(tags)
        return [
            TutorialType(**to_strawberry_dict(tutorial)) for tutorial in tutorials
        ]
