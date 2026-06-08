"""Background worker to permanently delete accounts whose grace period has expired.

Apple App Store Guideline 5.1.1(v) requires that users can initiate account
deletion from within the app. Llego apps offer a 30-day grace period via the
`requestAccountDeletion` mutation, which sets `User.scheduledDeletionAt`.
This worker is responsible for the actual hard delete once that timestamp passes.
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId

from clients import get_database
from repositories import users_repo
from utils.s3 import delete_file

logger = logging.getLogger(__name__)


async def delete_expired_accounts() -> int:
    """Hard-delete users whose `scheduledDeletionAt` is in the past.

    Returns the number of accounts removed.
    """
    db = get_database()
    now = datetime.now(timezone.utc)

    cursor = db["users"].find(
        {"scheduledDeletionAt": {"$ne": None, "$lte": now}},
        {"_id": 1, "avatar": 1},
    )
    expired = await cursor.to_list(length=None)

    removed = 0
    for doc in expired:
        user_id = str(doc["_id"])
        avatar = doc.get("avatar")
        try:
            if avatar:
                try:
                    await delete_file(avatar)
                except Exception as exc:
                    logger.warning(f"Could not delete avatar for {user_id}: {exc}")
            success = await users_repo.delete(user_id)
            if success:
                removed += 1
                logger.info(f"Account {user_id} permanently deleted (grace period expired)")
        except Exception as exc:
            logger.error(f"Error deleting expired account {user_id}: {exc}", exc_info=True)

    return removed
