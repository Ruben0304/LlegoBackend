"""TronDealer payment integration service.

Flow:
  1. create_wallet()  → calls POST https://api.trondealer.com/v1/create-wallet
                        saves TronDealerWallet (address → orderId mapping) in DB.
                        TronDealer auto-sweeps received USDT to the master wallet
                        configured in the TronDealer dashboard.
  2. handle_webhook() → receives POST /api/v1/webhooks/trondealer
                        validates HMAC-SHA256 signature, checks allowed IP whitelist,
                        deduplicates by wallet address (atomic find_and_update on PENDING),
                        marks order PAID, creates PendingPayout.
"""

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Optional

import httpx
from bson import ObjectId
from pydantic import BaseModel

from clients.mongodb_client import get_database
from core.config import settings
from domain.crypto_payments import PendingPayout, TronDealerWallet, TronDealerWalletStatus
from repositories.trondealer_repository import TronDealerRepository
from repositories.payout_repository import PayoutRepository

logger = logging.getLogger(__name__)

TRONDEALER_API_BASE = "https://api.trondealer.com/v1"


# ---------------------------------------------------------------------------
# Pydantic schemas for TronDealer API interaction
# ---------------------------------------------------------------------------


class TronDealerCreateWalletResponse(BaseModel):
    """
    Response from POST /v1/create-wallet.
    Field names are based on TronDealer REST API v1/v2 conventions.
    Adjust if TronDealer changes their schema.
    """
    address: str
    # TronDealer may return additional fields; capture them loosely.
    network: Optional[str] = None
    token: Optional[str] = None

    class Config:
        extra = "allow"


class TronDealerWebhookPayload(BaseModel):
    """
    Webhook payload sent by TronDealer on confirmed deposit.
    Signature: HMAC-SHA256 of the raw request body with webhook_secret,
    delivered in the X-TronDealer-Signature header.
    """
    address: str            # wallet that received the deposit
    amount: str             # string number, e.g. "10.00"
    token: str              # "USDT" | "USDC" etc.
    txhash: str             # blockchain tx hash
    confirmations: int = 1

    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TronDealerService:
    def __init__(
        self,
        wallets_repo: TronDealerRepository,
        payouts_repo: PayoutRepository,
    ):
        self._wallets = wallets_repo
        self._payouts = payouts_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_wallet(
        self,
        order_id: str,
        branch_id: str,
        business_id: str,
        expected_amount: float,
    ) -> TronDealerCreateWalletResponse:
        """
        Request a dedicated deposit wallet from TronDealer for this order.
        TronDealer will auto-sweep any incoming funds to your master wallet.
        Returns the wallet address to show the customer.
        """
        if not settings.trondealer_api_key:
            raise RuntimeError("TronDealer API key not configured.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{TRONDEALER_API_BASE}/create-wallet",
                json={"order_id": order_id},
                headers={
                    "Authorization": f"Bearer {settings.trondealer_api_key}",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code not in (200, 201):
            logger.error(
                "TronDealer create-wallet failed order=%s status=%s body=%s",
                order_id,
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"TronDealer API error: {response.status_code} {response.text}"
            )

        data = response.json()
        wallet_resp = TronDealerCreateWalletResponse(**data)

        # Persist wallet mapping
        wallet = TronDealerWallet(
            _id=ObjectId(),
            orderId=ObjectId(order_id),
            branchId=ObjectId(branch_id),
            businessId=ObjectId(business_id),
            address=wallet_resp.address,
            expectedAmount=expected_amount,
            status=TronDealerWalletStatus.PENDING,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
        await self._wallets.create(wallet)

        logger.info(
            "TronDealer wallet created order=%s address=%s",
            order_id,
            wallet_resp.address,
        )
        return wallet_resp

    async def handle_webhook(
        self,
        raw_body: bytes,
        signature_header: Optional[str],
        client_ip: Optional[str],
        payload: TronDealerWebhookPayload,
    ) -> bool:
        """
        Process an incoming TronDealer deposit webhook.

        Returns True if processed (new), False if duplicate.
        Raises ValueError on security violation.
        """
        # 1. IP whitelist check
        self._verify_ip(client_ip)

        # 2. HMAC signature validation
        self._verify_signature(raw_body, signature_header)

        # 3. Idempotency: atomic mark_completed on PENDING wallet
        received = float(payload.amount)
        wallet = await self._wallets.mark_completed(
            address=payload.address,
            received_amount=received,
            tx_hash=payload.txhash,
            token=payload.token,
            confirmations=payload.confirmations,
        )
        if wallet is None:
            existing = await self._wallets.get_by_address(payload.address)
            if existing and existing.status == TronDealerWalletStatus.COMPLETED:
                logger.info(
                    "TronDealer duplicate webhook ignored address=%s txhash=%s",
                    payload.address,
                    payload.txhash,
                )
                return False
            logger.warning(
                "TronDealer webhook: wallet not found for address=%s", payload.address
            )
            return False

        logger.info(
            "TronDealer payment confirmed order=%s address=%s amount=%s %s txhash=%s",
            str(wallet.orderId),
            payload.address,
            received,
            payload.token,
            payload.txhash,
        )

        # 4. Mark order as PAID (same pattern as payments_service.py)
        db = get_database()
        await db.orders.update_one(
            {"_id": wallet.orderId},
            {
                "$set": {
                    "paymentStatus": "completed",
                    "paidAt": datetime.utcnow(),
                    "status": "pending_acceptance",
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

        # 5. Register pending payout
        payout = PendingPayout(
            _id=ObjectId(),
            orderId=wallet.orderId,
            branchId=wallet.branchId,
            businessId=wallet.businessId,
            amount=received,
            currency="usd",
            gateway="trondealer",
            externalTransactionId=payload.txhash,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
        )
        await self._payouts.create(payout)

        logger.info(
            "PendingPayout created gateway=trondealer order=%s amount=%s",
            str(wallet.orderId),
            received,
        )
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _verify_ip(self, client_ip: Optional[str]) -> None:
        """Block requests from non-whitelisted IPs if a whitelist is configured."""
        whitelist_str = settings.trondealer_allowed_ips.strip()
        if not whitelist_str:
            return  # no whitelist configured — allow all

        allowed = {ip.strip() for ip in whitelist_str.split(",") if ip.strip()}
        if client_ip not in allowed:
            logger.warning(
                "TronDealer webhook rejected — IP %s not in whitelist", client_ip
            )
            raise ValueError(f"IP {client_ip} not in TronDealer whitelist.")

    def _verify_signature(self, raw_body: bytes, signature_header: Optional[str]) -> None:
        """
        Verify HMAC-SHA256 signature of the raw request body.
        TronDealer sends the hex digest in X-TronDealer-Signature.
        Skip if trondealer_webhook_secret is not configured (dev mode).
        """
        secret = settings.trondealer_webhook_secret
        if not secret:
            logger.debug("TronDealer webhook signature check skipped (no secret configured).")
            return

        if not signature_header:
            raise ValueError("Missing X-TronDealer-Signature header.")

        expected = hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature_header):
            raise ValueError("Invalid TronDealer webhook signature.")
