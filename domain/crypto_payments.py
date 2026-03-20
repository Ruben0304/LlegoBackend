"""Domain models for QvaPay and TronDealer payment integrations."""

from datetime import datetime
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class QvaPayInvoiceStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class QvaPayInvoice(BaseModel):
    """
    Invoice created via QvaPay API.

    Tracks the lifecycle of a QvaPay payment from creation to completion.
    transactionUuid is used for idempotency on webhook deduplication.
    """

    id: PyObjectId = Field(alias="_id")
    orderId: PyObjectId
    branchId: PyObjectId
    businessId: PyObjectId

    # QvaPay identifiers
    transactionUuid: str  # QvaPay's transaction_uuid — used as idempotency key
    remoteId: str  # our orderId sent as remote_id to QvaPay

    # Payment details
    amount: float
    description: str
    paymentUrl: Optional[str] = None  # shareable URL for the customer
    expireAt: Optional[datetime] = None

    # Status tracking
    status: QvaPayInvoiceStatus = QvaPayInvoiceStatus.PENDING
    completedAt: Optional[datetime] = None
    webhookReceivedAt: Optional[datetime] = None  # timestamp of first valid webhook

    # Audit
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True


class TronDealerWalletStatus(str, Enum):
    PENDING = "pending"       # wallet assigned, awaiting deposit
    COMPLETED = "completed"   # deposit confirmed by webhook
    FAILED = "failed"
    EXPIRED = "expired"


class TronDealerWallet(BaseModel):
    """
    TRON/USDT wallet assigned per transaction via TronDealer API.

    TronDealer auto-sweeps received funds to the master wallet configured
    in their dashboard. We keep a mapping of address → orderId for webhook routing.
    The address field is the idempotency key for webhook deduplication.
    """

    id: PyObjectId = Field(alias="_id")
    orderId: PyObjectId
    branchId: PyObjectId
    businessId: PyObjectId

    # TronDealer identifiers
    address: str  # wallet address — unique key for webhook routing
    expectedAmount: float  # USDT amount expected

    # Status tracking
    status: TronDealerWalletStatus = TronDealerWalletStatus.PENDING
    receivedAmount: Optional[float] = None
    txHash: Optional[str] = None         # blockchain transaction hash
    token: Optional[str] = None          # "USDT", "USDC", etc.
    confirmations: Optional[int] = None
    completedAt: Optional[datetime] = None
    webhookReceivedAt: Optional[datetime] = None  # timestamp of first valid webhook

    # Audit
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True


class PayoutStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PendingPayout(BaseModel):
    """
    Records a completed payment that requires manual liquidation to a third party
    (delivery person, merchant, etc.).

    Created automatically when a QvaPay or TronDealer webhook marks an order PAID.
    An admin confirms the payout via POST /admin/payouts/{id}/confirm once the
    manual transfer has been executed.
    """

    id: PyObjectId = Field(alias="_id")
    orderId: PyObjectId
    branchId: PyObjectId
    businessId: PyObjectId

    # Payment details
    amount: float
    currency: str = "usd"           # always USD for QvaPay/TronDealer

    # Gateway info
    gateway: str                    # "qvapay" | "trondealer"
    externalTransactionId: str      # QvaPay transaction_uuid or TronDealer txHash/address

    # Payout status
    payoutStatus: PayoutStatus = PayoutStatus.PENDING
    confirmedBy: Optional[PyObjectId] = None   # admin user ID
    confirmedAt: Optional[datetime] = None
    notes: Optional[str] = None

    # Audit
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True


__all__ = [
    "QvaPayInvoice",
    "QvaPayInvoiceStatus",
    "TronDealerWallet",
    "TronDealerWalletStatus",
    "PendingPayout",
    "PayoutStatus",
]
