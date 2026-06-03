"""GraphQL type definitions for PromotionalVideo entity."""
import strawberry
from typing import List, Optional
from datetime import datetime
from strawberry.types import Info

from utils.s3 import generate_presigned_url

from ..tutorials.types import AppTarget


@strawberry.type
class PromotionalVideoType:
    """Promotional video GraphQL type (Instagram-stories style)."""
    id: str
    title: str
    description: str
    videoUrl: str
    duration: int
    appTarget: AppTarget
    thumbnailUrl: Optional[str]
    branchId: Optional[str]
    order: int
    isActive: bool
    tags: List[str]
    createdAt: datetime
    updatedAt: Optional[datetime]

    @strawberry.field(description="Presigned URL for the promo video")
    def video_url_signed(self) -> str:
        """Generate presigned URL for video."""
        return generate_presigned_url(self.videoUrl)

    @strawberry.field(description="Presigned URL for the promo thumbnail")
    def thumbnail_url_signed(self) -> Optional[str]:
        """Generate presigned URL for thumbnail."""
        if self.thumbnailUrl:
            return generate_presigned_url(self.thumbnailUrl)
        return None

    @strawberry.field(description="Name of the branch that uploaded the promo (optional)")
    async def branch_name(self, info: Info) -> Optional[str]:
        """Resolve the uploading branch name for the stories header."""
        if not self.branchId:
            return None
        from repositories import branches_repo

        branch = await branches_repo.get_by_id(self.branchId)
        return branch.name if branch else None

    @strawberry.field(
        description="Presigned avatar URL of the branch that uploaded the promo (optional)"
    )
    async def branch_avatar_url(self, info: Info) -> Optional[str]:
        """Resolve the uploading branch avatar (inherits business avatar)."""
        if not self.branchId:
            return None
        from repositories import branches_repo
        from ..branches.types import _resolve_branch_avatar_path

        branch = await branches_repo.get_by_id(self.branchId)
        if not branch:
            return None

        avatar_path = await _resolve_branch_avatar_path(branch.businessId, branch.avatar)
        if avatar_path:
            return generate_presigned_url(avatar_path)
        return None
