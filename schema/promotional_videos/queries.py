"""GraphQL query resolvers for PromotionalVideo entity."""

from typing import List, Optional

import strawberry
from strawberry.types import Info

from repositories import promotional_videos_repo
from utils.rate_limit import rate_limit_graphql
from utils.serialization import to_strawberry_dict

from ..tutorials.types import AppTarget
from .types import PromotionalVideoType


@strawberry.type
class PromotionalVideoQuery:
    @strawberry.field(description="Get all promotional videos")
    async def promotional_videos(self, info: Info) -> List[PromotionalVideoType]:
        """Get all promotional videos ordered by order field."""
        rate_limit_graphql(info, "graphql")
        videos = await promotional_videos_repo.get_all()
        return [
            PromotionalVideoType(**to_strawberry_dict(video)) for video in videos
        ]

    @strawberry.field(description="Get active promotional videos only")
    async def active_promotional_videos(self, info: Info) -> List[PromotionalVideoType]:
        """Get all active promotional videos ordered by order field."""
        rate_limit_graphql(info, "graphql")
        videos = await promotional_videos_repo.get_active()
        return [
            PromotionalVideoType(**to_strawberry_dict(video)) for video in videos
        ]

    @strawberry.field(description="Get promotional videos by app target")
    async def promotional_videos_by_app(
        self, info: Info, appTarget: AppTarget
    ) -> List[PromotionalVideoType]:
        """Get promotional videos filtered by app target (includes 'both')."""
        rate_limit_graphql(info, "graphql")
        videos = await promotional_videos_repo.get_by_app_target(appTarget.value)
        return [
            PromotionalVideoType(**to_strawberry_dict(video)) for video in videos
        ]

    @strawberry.field(description="Get promotional video by ID")
    async def promotional_video(
        self, info: Info, id: str
    ) -> Optional[PromotionalVideoType]:
        """Get a single promotional video by ID."""
        rate_limit_graphql(info, "graphql")
        video = await promotional_videos_repo.get_by_id(id)
        if video:
            return PromotionalVideoType(**to_strawberry_dict(video))
        return None

    @strawberry.field(description="Get promotional videos uploaded by a branch")
    async def promotional_videos_by_branch(
        self, info: Info, branchId: str
    ) -> List[PromotionalVideoType]:
        """Get promotional videos uploaded by a specific branch."""
        rate_limit_graphql(info, "graphql")
        videos = await promotional_videos_repo.get_by_branch(branchId)
        return [
            PromotionalVideoType(**to_strawberry_dict(video)) for video in videos
        ]
