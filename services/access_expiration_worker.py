"""Background worker to expire temporary business and branch access."""
from repositories import business_access_repo, branch_invitations_repo
from services.access_manager import access_manager


async def expire_old_accesses() -> None:
    """Expire old business and branch access records."""
    expired_accesses = await business_access_repo.get_expired_accesses()
    for access in expired_accesses:
        try:
            await access_manager.revoke_business_access(access.id, revoked_by=None)
        except Exception as exc:
            print(f"Error expiring business access {access.id}: {exc}")

    expired_invitations = await branch_invitations_repo.get_expired_branch_invitations()
    for invitation in expired_invitations:
        if not invitation.usedBy or not invitation.branchId:
            continue

        try:
            active_business_access = await business_access_repo.get_by_user_and_business(
                invitation.usedBy,
                invitation.businessId
            )
            if active_business_access:
                continue

            await access_manager.revoke_branch_access(invitation.usedBy, invitation.branchId)
        except Exception as exc:
            print(f"Error expiring branch invitation {invitation.id}: {exc}")
