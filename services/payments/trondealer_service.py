"""TronDealer payment integration service.

Flow:
  1. create_wallet()  → calls POST https://api.trondealer.com/v1/create-wallet
                        saves TronDealerWallet (address → orderId mapping) in DB.
                        TronDealer auto-sweeps received USDT to the master wallet
                        configured in the TronDealer dashboard.
  2. handle_webhook() → receives POST /api/v1/webhooks/trondealer
                        validates HMAC-SHA256 signature, checks allowed IP whitelist,
                        deduplicates by wallet address (atomic find_and_update on PENDING),
                        checks the deposit against expectedAmount, marks order
                        PAID, creates PendingPayout. If less arrived, the wallet
                        is UNDERPAID and the order requiresAttention.
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
from domain.crypto_payments import (
    PendingPayout,
    TronDealerWallet,
    TronDealerWalletStatus,
)
from repositories.payout_repository import PayoutRepository
from repositories.trondealer_repository import TronDealerRepository
from services.payments.webhook_amounts import (
    flag_underpaid_order,
    is_underpaid,
    parse_amount,
    underpayment_reason,
)

logger = logging.getLogger(__name__)

TRONDEALER_API_BASE = "https://trondealer.com/api/v2"


# ---------------------------------------------------------------------------
# Pydantic schemas for TronDealer API interaction
# ---------------------------------------------------------------------------


class TronDealerWalletData(BaseModel):
    """Wallet data from TronDealer API v2."""

    id: str
    address: str
    label: Optional[str] = None
    status: str
    created_at: str


class TronDealerCreateWalletResponse(BaseModel):
    """
    Response from POST /api/v2/wallets/assign.
    Based on TronDealer API v2 documentation.
    """

    success: bool
    wallet: TronDealerWalletData

    # Alias for backward compatibility
    @property
    def address(self) -> str:
        return self.wallet.address

    @property
    def wallet_address(self) -> str:
        return self.wallet.address

    # Default values for fields not provided by API v2
    @property
    def token(self) -> str:
        """Default token is USDT on BSC."""
        return "USDT"

    @property
    def network(self) -> str:
        """TronDealer API v2 uses BSC (BEP20)."""
        return "BSC"

    class Config:
        extra = "allow"


class TronDealerWebhookPayload(BaseModel):
    """
    Webhook payload sent by TronDealer on confirmed deposit.
    Signature: HMAC-SHA256 of the raw request body with webhook_secret,
    delivered in the X-TronDealer-Signature header.
    """

    address: str  # wallet that received the deposit
    amount: str  # string number, e.g. "10.00"
    token: str  # "USDT" | "USDC" etc.
    txhash: str  # blockchain tx hash
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
                f"{TRONDEALER_API_BASE}/wallets/assign",
                json={
                    "client_id": settings.trondealer_business_id,
                    "order_id": order_id,
                },
                headers={
                    "x-api-key": settings.trondealer_api_key,
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

        # Persist wallet mapping (use .address property for compatibility)
        wallet = TronDealerWallet(
            _id=ObjectId(),
            orderId=ObjectId(order_id),
            branchId=ObjectId(branch_id),
            businessId=ObjectId(business_id),
            address=wallet_resp.address,  # Uses property for backward compatibility
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

        # 3. Monto: el deposito debe cubrir expectedAmount (con tolerancia de
        # redondeo). Si llega menos, no se completa el pago ni se genera payout:
        # el pedido queda para revision de un admin.
        received = parse_amount(payload.amount)
        existing = await self._wallets.get_by_address(payload.address)
        if existing is None:
            logger.warning(
                "TronDealer webhook: wallet not found for address=%s", payload.address
            )
            return False
        if existing.status != TronDealerWalletStatus.PENDING:
            if (
                existing.status == TronDealerWalletStatus.UNDERPAID
                and existing.txHash != payload.txhash
            ):
                # Deposito adicional sobre una wallet que ya recibio de menos:
                # no se suma solo; se deja constancia para soporte.
                logger.warning(
                    "TronDealer extra deposit on underpaid wallet order=%s address=%s "
                    "amount=%s txhash=%s",
                    str(existing.orderId),
                    payload.address,
                    received,
                    payload.txhash,
                )
                reason = underpayment_reason(
                    "USDT",
                    existing.receivedAmount,
                    existing.expectedAmount,
                    existing.txHash or payload.address,
                )
                await flag_underpaid_order(
                    str(existing.orderId),
                    f"{reason} Despues llego otro deposito de {payload.amount} "
                    f"(tx {payload.txhash}).",
                )
                return False
            logger.info(
                "TronDealer duplicate webhook ignored address=%s txhash=%s status=%s",
                payload.address,
                payload.txhash,
                existing.status,
            )
            return False

        if is_underpaid(received, existing.expectedAmount):
            return await self._handle_underpayment(existing, payload, received)

        # 4. Idempotency: atomic mark_completed on PENDING wallet
        wallet = await self._wallets.mark_completed(
            address=payload.address,
            received_amount=received,
            tx_hash=payload.txhash,
            token=payload.token,
            confirmations=payload.confirmations,
        )
        if wallet is None:
            # Otro webhook igual lo proceso en paralelo
            logger.info(
                "TronDealer duplicate webhook ignored address=%s txhash=%s",
                payload.address,
                payload.txhash,
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

        # 5. Mark order as PAID (same pattern as payments_service.py)
        db = get_database()
        order_doc = await db.orders.find_one({"_id": wallet.orderId}, {"status": 1})
        current_status = (order_doc or {}).get("status")
        if current_status == "pending_payment":
            next_status = "accepted"
        elif current_status == "accepted":
            next_status = "accepted"
        else:
            next_status = current_status or "accepted"
        await db.orders.update_one(
            {"_id": wallet.orderId},
            {
                "$set": {
                    "paymentStatus": "completed",
                    "paidAt": datetime.utcnow(),
                    "status": next_status,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

        # 6. Register pending payout
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

    async def _handle_underpayment(
        self,
        wallet: TronDealerWallet,
        payload: TronDealerWebhookPayload,
        received: Optional[float],
    ) -> bool:
        """Llego menos de expectedAmount: wallet UNDERPAID, pedido sin pagar y
        marcado para revision, y sin payout."""
        claimed = await self._wallets.mark_underpaid(
            address=payload.address,
            received_amount=received,
            tx_hash=payload.txhash,
            token=payload.token,
            confirmations=payload.confirmations,
        )
        if claimed is None:
            logger.info(
                "TronDealer duplicate webhook ignored address=%s txhash=%s",
                payload.address,
                payload.txhash,
            )
            return False

        reason = underpayment_reason(
            "USDT", received, wallet.expectedAmount, payload.txhash
        )
        logger.warning(
            "TronDealer underpayment order=%s address=%s received=%s expected=%s "
            "raw_amount=%r txhash=%s",
            str(wallet.orderId),
            payload.address,
            received,
            wallet.expectedAmount,
            payload.amount,
            payload.txhash,
        )
        await flag_underpaid_order(str(wallet.orderId), reason)
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

    def _verify_signature(
        self, raw_body: bytes, signature_header: Optional[str]
    ) -> None:
        """
        Verify HMAC-SHA256 signature of the raw request body.
        TronDealer sends the hex digest in X-TronDealer-Signature.
        Skip if trondealer_webhook_secret is not configured (dev mode).
        """
        secret = settings.trondealer_webhook_secret
        if not secret:
            logger.debug(
                "TronDealer webhook signature check skipped (no secret configured)."
            )
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
