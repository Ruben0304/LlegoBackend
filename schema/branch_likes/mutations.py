"""GraphQL mutations for BranchLikes entity."""
import strawberry
from typing import Optional
from strawberry.types import Info

from .types import BranchLikeType
from repositories import branch_likes_repo
from utils.graphql_auth import require_auth


@strawberry.type
class BranchLikesMutation:
    @strawberry.mutation(description="Agregar like a un branch")
    async def like_branch(
        self,
        info: Info,
        branch_id: str,
        jwt: Optional[str] = None
    ) -> BranchLikeType:
        """
        Add a like to a branch.
        Raises exception if already liked.
        """
        user_id = require_auth(jwt, info)

        result = await branch_likes_repo.add(user_id, branch_id)

        if not result:
            raise Exception("Ya te gusta este branch")

        return BranchLikeType(
            id=result.id,
            userId=result.userId,
            branchId=result.branchId,
            createdAt=result.createdAt
        )

    @strawberry.mutation(description="Remover like de un branch")
    async def unlike_branch(
        self,
        info: Info,
        branch_id: str,
        jwt: Optional[str] = None
    ) -> bool:
        """Remove a like from a branch."""
        user_id = require_auth(jwt, info)

        success = await branch_likes_repo.remove(user_id, branch_id)

        if not success:
            raise Exception("No le tenías like a este branch")

        return True
