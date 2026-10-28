"""GraphQL type definitions for branch menu OCR."""

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from strawberry.types import Info

from services.menu_ocr_utils import QUALITY_MESSAGES_ES
from utils.s3 import get_public_url


@strawberry.type
class MenuQualityType:
    """Quality assessment results for menu OCR."""

    verdict: str  # "good", "fair", "bad"
    reasons: list[str]  # List of quality issue keys
    tips: list[str]  # List of improvement tips
    messages: list[str]  # Human-readable messages in Spanish


@strawberry.type
class MenuMatchType:
    """A match of the search query within a menu line."""

    lineIndex: int  # Index of the line containing the match
    start: int  # Start character position in the line
    end: int  # End character position in the line
    text: str  # Matched text substring
    polygon: list[list[float]]  # 4 normalized points [[x, y], ...]


@strawberry.type
class BranchMenuType:
    """Menu OCR data for a branch."""

    id: str
    branchId: str
    image: str  # Relative S3 path
    isActive: bool
    ocrStatus: str  # "pending", "processing", "done", "failed"
    ocrError: Optional[str]
    quality: Optional[MenuQualityType]
    createdAt: datetime
    updatedAt: datetime

    @strawberry.field(description="Public URL for the menu image")
    def image_url(self) -> str:
        return get_public_url(self.image)


@strawberry.type
class MenuSearchResultType:
    """Search result containing menu and matches."""

    menu: BranchMenuType
    matchCount: int
    matches: list[MenuMatchType]

    @strawberry.field(description="Branch associated with this menu")
    async def branch(
        self, info: Info
    ) -> Optional[Annotated["BranchType", strawberry.lazy("schema.branches.types")]]:
        """Resolve the branch using DataLoader."""
        from schema.branches.types import BranchType
        from schema.branches.utils import branch_to_dict

        loader = info.context.get("branch_loader")
        if loader:
            branch_data = await loader.load(str(self.menu.branchId))
        else:
            from repositories import branches_repo

            branch_data = await branches_repo.get_by_id(str(self.menu.branchId))

        if branch_data:
            return BranchType(**branch_to_dict(branch_data))
        return None


def menu_to_type(menu) -> BranchMenuType:
    """Convert BranchMenu domain model to GraphQL type."""
    quality = None
    if menu.quality:
        # Build messages list from quality reasons and tips
        messages = []
        for key in menu.quality.get("reasons", []):
            if key in QUALITY_MESSAGES_ES:
                messages.append(QUALITY_MESSAGES_ES[key])
        for key in menu.quality.get("tips", []):
            if key in QUALITY_MESSAGES_ES:
                messages.append(QUALITY_MESSAGES_ES[key])

        quality = MenuQualityType(
            verdict=menu.quality.get("verdict", "fair"),
            reasons=menu.quality.get("reasons", []),
            tips=menu.quality.get("tips", []),
            messages=messages,
        )

    return BranchMenuType(
        id=str(menu.id),
        branchId=str(menu.branchId),
        image=menu.image,
        isActive=menu.isActive,
        ocrStatus=menu.ocrStatus,
        ocrError=menu.ocrError,
        quality=quality,
        createdAt=menu.createdAt,
        updatedAt=menu.updatedAt,
    )
