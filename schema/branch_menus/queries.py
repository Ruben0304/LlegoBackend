"""GraphQL query resolvers for branch menu OCR."""

from typing import Optional

import strawberry
from strawberry.types import Info

from repositories import branch_menus_repo
from services.menu_search_service import search_menus
from utils.graphql_auth import apply_optional_jwt
from utils.rate_limit import rate_limit_graphql

from .types import BranchMenuType, MenuSearchResultType, menu_to_type, MenuMatchType


@strawberry.type
class BranchMenuQuery:
    @strawberry.field(description="Get active menu for a branch")
    async def branch_menu(
        self, info: Info, branch_id: str, jwt: Optional[str] = None
    ) -> Optional[BranchMenuType]:
        """Get the active menu for a branch if it exists and is active."""
        apply_optional_jwt(jwt, info)

        menu = await branch_menus_repo.get_by_branch(branch_id)
        if not menu:
            return None

        # Only return if active, or if user is authenticated and has access
        if menu.isActive:
            return menu_to_type(menu)

        # Check if authenticated user has access to this branch
        user_id = info.context.get("user_id")
        if not user_id:
            return None

        # Try to check access
        try:
            from services.access_checker import access_checker

            has_access, _ = await access_checker.check_branch_access(user_id, branch_id)
            if has_access:
                return menu_to_type(menu)
        except Exception:
            pass

        return None

    @strawberry.field(description="Search menus by query text")
    async def search_menus(
        self,
        info: Info,
        query: str,
        branch_tipo: Optional[str] = None,
        first: int = 10,
        jwt: Optional[str] = None,
    ) -> list[MenuSearchResultType]:
        """
        Search menus by query text.

        Args:
            query: Search term (must have >= 3 alphanumeric chars)
            branch_tipo: Optional branch type to filter by
            first: Maximum results (capped at 20)
            jwt: Optional JWT token

        Returns:
            List of search results with menus and matches
        """
        apply_optional_jwt(jwt, info)
        rate_limit_graphql(info, "menu_search")

        if first < 1:
            raise ValueError("first debe ser mayor que cero")

        # Limit first to maximum
        first = min(first, 20)

        # Only branches of approved businesses are searchable. No try/except on
        # purpose: if this lookup fails the search must fail, not widen its scope.
        if branch_tipo:
            from services.feed_service import feed_service

            branch_ids = list(await feed_service.get_branch_ids_by_tipo(branch_tipo))
        else:
            from repositories import branches_repo, businesses_repo

            approved = await businesses_repo.get_ids_by_approval_status("approved")
            branch_ids = await branches_repo.get_ids_by_business_ids(approved)

        # Call service
        try:
            results = await search_menus(query, branch_ids=branch_ids, limit=first)
        except ValueError as e:
            raise Exception(str(e))

        # Convert to GraphQL types
        graphql_results = []
        for result in results:
            menu_type = menu_to_type(result["menu"])
            matches = [
                MenuMatchType(
                    lineIndex=m["lineIndex"],
                    start=m["start"],
                    end=m["end"],
                    text=m["text"],
                    polygon=m["polygon"],
                )
                for m in result["matches"]
            ]
            graphql_results.append(
                MenuSearchResultType(
                    menu=menu_type,
                    matchCount=result["matchCount"],
                    matches=matches,
                )
            )

        return graphql_results
