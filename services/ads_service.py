"""Business logic for ad campaigns (paid feed visibility).

Keeps the GraphQL layer thin: pricing, purchase/billing and feed selection live
here. Billing reuses the wallet rail directly (branch wallet -> platform wallet);
Stripe and CUP-transfer payment are wired in a follow-up step (see
``purchase_campaign``).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from clients import get_database
from domain.ads import (
    CAMPAIGN_PLACEMENTS,
    AdCampaign,
    AdPricing,
)
from repositories import (
    ad_campaigns_repo,
    ad_pricing_repo,
    branches_repo,
    payment_methods_repo,
    platform_repo,
)


def _oid(value: Any) -> Any:
    try:
        return ObjectId(value)
    except Exception:
        return value


class AdsService:
    """Service for ad campaign pricing, purchase and feed selection."""

    # -- Pricing ---------------------------------------------------------------

    async def get_pricing(self) -> List[AdPricing]:
        return await ad_pricing_repo.get_all_active()

    async def quote(self, placement: str, duration_days: int) -> AdPricing:
        """Resolve the fixed price for a (placement, duration). Raises if missing."""
        if placement not in CAMPAIGN_PLACEMENTS:
            raise Exception(f"Placement inválido: {placement}")
        pricing = await ad_pricing_repo.get(placement, duration_days)
        if not pricing:
            raise Exception(
                "No hay tarifa configurada para esa combinación de placement y duración"
            )
        return pricing

    # -- Purchase / billing ----------------------------------------------------

    async def purchase_campaign(
        self, campaign: AdCampaign, payment_method_id: str
    ) -> AdCampaign:
        """Charge the campaign's fixed fee and move it into moderation.

        Wallet payment is processed immediately (branch wallet -> platform).
        Stripe / CUP-transfer are recorded as pending_payment for the dedicated
        confirmation flow added in the payments slice.
        """
        method = await payment_methods_repo.get_by_id(payment_method_id)
        if not method:
            raise Exception("Método de pago no encontrado")

        method_kind = getattr(method, "method", None) or getattr(method, "code", "")

        if method_kind == "wallet":
            await self._charge_branch_wallet(campaign)
            return await ad_campaigns_repo.update(
                str(campaign.id),
                {
                    "paymentMethodId": payment_method_id,
                    "paymentStatus": "paid",
                    "status": "pending_review",
                },
            )

        # Stripe / transfer: keep the campaign in pending_payment. The payments
        # slice attaches a PaymentAttempt (purpose="campaign") and flips this to
        # paid -> pending_review on Stripe webhook / transfer-proof confirmation.
        return await ad_campaigns_repo.update(
            str(campaign.id),
            {
                "paymentMethodId": payment_method_id,
                "paymentStatus": "pending_proof"
                if method_kind == "transfer"
                else "unpaid",
                "status": "pending_payment",
            },
        )

    async def _charge_branch_wallet(self, campaign: AdCampaign) -> None:
        """Atomically debit the branch wallet and credit the platform wallet."""
        amount = float(campaign.price)
        currency = campaign.currency  # "usd" | "local"
        if amount <= 0:
            raise Exception("El precio de la campaña no es válido")

        branch = await branches_repo.get_by_id(str(campaign.branchId))
        if not branch:
            raise Exception("Sucursal no encontrada")
        if getattr(branch, "walletStatus", "active") != "active":
            raise Exception("La wallet de la sucursal no está activa")

        db = get_database()
        # Atomic guarded debit — fails if balance is insufficient.
        result = await db.branches.update_one(
            {
                "_id": _oid(campaign.branchId),
                f"wallet.{currency}": {"$gte": amount},
            },
            {"$inc": {f"wallet.{currency}": -amount}},
        )
        if result.modified_count == 0:
            raise Exception("Saldo insuficiente en la wallet de la sucursal")

        # Credit platform wallet.
        await platform_repo.add_commission(amount, currency)

        # Record the wallet transaction (type "ad_spend" so it shows in history).
        tx_id = ObjectId()
        await db.wallet_transactions.insert_one(
            {
                "_id": tx_id,
                "fromOwnerId": _oid(campaign.branchId),
                "fromOwnerType": "branch",
                "toOwnerId": None,
                "toOwnerType": "platform",
                "amount": amount,
                "currency": currency,
                "type": "ad_spend",
                "status": "completed",
                "description": f"Campaña {campaign.placement}: {campaign.name}",
                "metadata": {"campaign_id": str(campaign.id)},
                "createdAt": datetime.utcnow(),
                "completedAt": datetime.utcnow(),
            }
        )
        await ad_campaigns_repo.update(str(campaign.id), {"paymentRef": str(tx_id)})

    # -- Moderation ------------------------------------------------------------

    async def approve(self, campaign: AdCampaign) -> AdCampaign:
        """Approve a paid campaign and open its active window now."""
        now = datetime.utcnow()
        start = campaign.startAt or now
        end = campaign.endAt or (start + timedelta(days=campaign.durationDays))
        return await ad_campaigns_repo.update(
            str(campaign.id),
            {
                "status": "active",
                "rejectionReason": None,
                "approvedAt": now,
                "rejectedAt": None,
                "startAt": start,
                "endAt": end,
            },
        )

    async def reject(self, campaign: AdCampaign, reason: Optional[str]) -> AdCampaign:
        return await ad_campaigns_repo.update(
            str(campaign.id),
            {
                "status": "rejected",
                "rejectionReason": reason,
                "rejectedAt": datetime.utcnow(),
                "approvedAt": None,
            },
        )

    # -- Feed selection --------------------------------------------------------

    async def get_feed_campaigns(
        self, placement: str, branch_ids: Any, limit: int = 8
    ) -> List[AdCampaign]:
        """Active campaigns for a placement, restricted to the feed's branches."""
        branch_ids = list(branch_ids or [])
        if not branch_ids:
            return []
        return await ad_campaigns_repo.list_active_for_feed(
            placement=placement, branch_ids=branch_ids, limit=limit
        )


ads_service = AdsService()
