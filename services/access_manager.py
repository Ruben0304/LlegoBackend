"""Access manager for granting and revoking branch/business access."""
from datetime import datetime
from typing import Optional, List

from bson import ObjectId

from clients.mongodb_client import get_database
from domain.models import BusinessAccess
from repositories import branches_repo, users_repo, business_access_repo
from utils.cache import invalidate_branch_cache


def _to_object_id(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return value


def _to_object_ids(values: List[str]) -> List[object]:
    return [_to_object_id(value) for value in values]


class AccessManager:
    """Centralized access management for branches and businesses."""

    async def grant_branch_access(self, user_id: str, branch_id: str) -> None:
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise Exception("Sucursal no encontrada")

        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        db = get_database()
        await db.branches.update_one(
            {"_id": _to_object_id(branch_id)},
            {"$addToSet": {"managerIds": _to_object_id(user_id)}}
        )
        await users_repo.add_branch_id(user_id, branch_id)

        invalidate_branch_cache(branch_id=branch_id)
        invalidate_branch_cache(business_id=branch.businessId)
        invalidate_branch_cache()

    async def revoke_branch_access(self, user_id: str, branch_id: str) -> None:
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            return

        db = get_database()
        await db.branches.update_one(
            {"_id": _to_object_id(branch_id)},
            {"$pull": {"managerIds": _to_object_id(user_id)}}
        )
        await users_repo.remove_branch_id(user_id, branch_id)

        invalidate_branch_cache(branch_id=branch_id)
        invalidate_branch_cache(business_id=branch.businessId)
        invalidate_branch_cache()

    async def grant_business_access(
        self,
        user_id: str,
        business_id: str,
        invitation_id: str,
        expires_at: Optional[datetime]
    ) -> BusinessAccess:
        user = await users_repo.get_by_id(user_id)
        if not user:
            raise Exception("Usuario no encontrado")

        access_id = str(ObjectId())
        access = BusinessAccess(
            id=access_id,
            userId=user_id,
            businessId=business_id,
            invitationId=invitation_id,
            grantedAt=datetime.utcnow(),
            expiresAt=expires_at,
            isActive=True
        )

        await business_access_repo.create(access)

        db = get_database()
        await db.branches.update_many(
            {"businessId": _to_object_id(business_id)},
            {"$addToSet": {"managerIds": _to_object_id(user_id)}}
        )

        branches = await branches_repo.get_by_business(business_id)
        branch_ids = [branch.id for branch in branches]

        add_updates = {"businessAccessIds": _to_object_id(access_id)}
        if branch_ids:
            add_updates["branchIds"] = {"$each": _to_object_ids(branch_ids)}

        await db.users.update_one(
            {"_id": _to_object_id(user_id)},
            {"$addToSet": add_updates}
        )

        invalidate_branch_cache(business_id=business_id)
        for branch_id in branch_ids:
            invalidate_branch_cache(branch_id=branch_id)
        invalidate_branch_cache()

        return access

    async def revoke_business_access(
        self,
        access_id: str,
        revoked_by: Optional[str] = None
    ) -> Optional[BusinessAccess]:
        access = await business_access_repo.get_by_id(access_id)
        if not access:
            return None

        if revoked_by:
            updated_access = await business_access_repo.revoke(access_id, revoked_by)
        else:
            updated_access = await business_access_repo.mark_as_expired(access_id)

        db = get_database()
        await db.branches.update_many(
            {"businessId": _to_object_id(access.businessId)},
            {"$pull": {"managerIds": _to_object_id(access.userId)}}
        )

        branches = await branches_repo.get_by_business(access.businessId)
        branch_ids = [branch.id for branch in branches]

        pull_updates = {"businessAccessIds": _to_object_id(access_id)}
        if branch_ids:
            pull_updates["branchIds"] = {"$in": _to_object_ids(branch_ids)}

        await db.users.update_one(
            {"_id": _to_object_id(access.userId)},
            {"$pull": pull_updates}
        )

        invalidate_branch_cache(business_id=access.businessId)
        for branch_id in branch_ids:
            invalidate_branch_cache(branch_id=branch_id)
        invalidate_branch_cache()

        return updated_access

    async def sync_business_access_to_new_branch(self, branch_id: str) -> None:
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            return

        accesses = await business_access_repo.get_active_by_business(branch.businessId)
        if not accesses:
            return

        user_ids = list({access.userId for access in accesses})
        if not user_ids:
            return

        db = get_database()
        await db.branches.update_one(
            {"_id": _to_object_id(branch_id)},
            {"$addToSet": {"managerIds": {"$each": _to_object_ids(user_ids)}}}
        )

        await db.users.update_many(
            {"_id": {"$in": _to_object_ids(user_ids)}},
            {"$addToSet": {"branchIds": _to_object_id(branch_id)}}
        )

        invalidate_branch_cache(branch_id=branch_id)
        invalidate_branch_cache(business_id=branch.businessId)
        invalidate_branch_cache()


access_manager = AccessManager()
