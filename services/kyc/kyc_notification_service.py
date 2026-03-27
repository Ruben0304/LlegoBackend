"""Notification service for KYC events to merchants."""

import logging
from typing import Dict

from repositories import (
    branches_repo,
    businesses_repo,
    device_token_repo,
)
from repositories.kyc_notification_log_repository import kyc_notification_logs_repo
from services.push_notification_service import push_service

logger = logging.getLogger(__name__)


class KycNotificationService:
    async def notify_merchant(
        self,
        *,
        kyc_verification_id: str,
        branch_id: str,
        event_type: str,
        title: str,
        body: str,
        data: Dict[str, str],
    ) -> Dict[str, int]:
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            return {"success": 0, "failed": 0}

        business = await businesses_repo.get_by_id(branch.businessId)
        manager_ids = {str(mid) for mid in (branch.managerIds or [])}
        if business:
            manager_ids.add(str(business.ownerId))

        all_tokens = await device_token_repo.get_all_active()
        merchant_tokens = [
            token.token
            for token in all_tokens
            if token.userId and str(token.userId) in manager_ids
        ]

        if not merchant_tokens:
            await kyc_notification_logs_repo.create(
                kyc_verification_id=kyc_verification_id,
                merchant_id=str(branch.businessId),
                event_type=event_type,
                channel="push",
                status="failed",
                attempts=1,
                last_error="NO_ACTIVE_TOKENS",
            )
            return {"success": 0, "failed": 0}

        result = await push_service.send_to_all(
            tokens=merchant_tokens,
            title=title,
            body=body,
            data=data,
            platform="IOS",
            bundle_id="com.llego.business.LlegoBusiness",
        )

        await kyc_notification_logs_repo.create(
            kyc_verification_id=kyc_verification_id,
            merchant_id=str(branch.businessId),
            event_type=event_type,
            channel="push",
            status="sent" if result.get("failed", 0) == 0 else "failed",
            attempts=1,
            last_error=None if result.get("failed", 0) == 0 else "PARTIAL_FAILURE",
        )
        return result


kyc_notification_service = KycNotificationService()
