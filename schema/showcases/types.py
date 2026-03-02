"""GraphQL type definitions for Showcase entity."""

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from strawberry.types import Info

from utils.s3 import generate_presigned_url


@strawberry.type
class ShowcaseItemType:
    id: str
    name: str
    description: Optional[str]
    price: Optional[float]
    availability: bool


@strawberry.type
class ShowcaseType:
    id: str
    branchId: str
    title: str
    image: str
    description: Optional[str]
    items: Optional[list[ShowcaseItemType]] = None
    isActive: bool
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Presigned URL for the showcase image")
    def image_url(self) -> str:
        return generate_presigned_url(self.image)

    @strawberry.field(description="Branch associated with this showcase")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        from schema.branches.types import BranchType
        from schema.branches.utils import branch_to_dict

        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(str(self.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(self.branchId)

        if branch_data:
            return BranchType(**branch_to_dict(branch_data))
        return None


def showcase_to_type(showcase) -> ShowcaseType:
    """Convert Showcase domain model to GraphQL type."""
    items = None
    if showcase.items is not None:
        items = [
            ShowcaseItemType(
                id=item.id,
                name=item.name,
                description=item.description,
                price=item.price,
                availability=item.availability,
            )
            for item in showcase.items
        ]

    return ShowcaseType(
        id=str(showcase.id),
        branchId=str(showcase.branchId),
        title=showcase.title,
        image=showcase.image,
        description=showcase.description,
        items=items,
        isActive=showcase.isActive,
        createdAt=showcase.createdAt,
        updatedAt=showcase.updatedAt,
    )
