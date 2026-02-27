"""Payment attempt models and enums."""
from pydantic import BaseModel, Field
from typing import Optional, Union
from datetime import datetime
from enum import Enum
from bson import ObjectId

from .py_object_id import PyObjectId


class PaymentAttemptStatus(str, Enum):
    """Status of a payment attempt."""

    # Initial states
    PENDING = "pending"  # Just created
    PROCESSING = "processing"  # In process (Stripe, wallet debiting)

    # Manual payment states
    AWAITING_PROOF = "awaiting_proof"  # Waiting for customer to upload proof
    AWAITING_BUSINESS = "awaiting_business"  # Waiting for business confirmation

    # Cash payment states
    AWAITING_DELIVERY = "awaiting_delivery"  # Cash payment, waiting for delivery confirmation

    # Final states
    COMPLETED = "completed"  # Payment successful
    FAILED = "failed"  # Payment failed
    EXPIRED = "expired"  # Timed out
    CANCELLED = "cancelled"  # Cancelled by user or system

    # Dispute states
    DISPUTED = "disputed"  # Business claims payment not received

    # Refund states
    REFUND_REQUESTED = "refund_requested"  # Customer requested refund
    REFUND_PROCESSING = "refund_processing"  # Refund in progress
    REFUNDED = "refunded"  # Refund completed


class PaymentAttempt(BaseModel):
    """
    Payment attempt for an order.

    Tracks the full lifecycle of a payment from initiation to completion,
    including refunds and disputes.
    """

    id: PyObjectId = Field(alias="_id")
    orderId: PyObjectId
    paymentMethodId: Union[PyObjectId, str]

    # Amounts (all calculated at payment initiation)
    subtotal: float  # Order items total
    deliveryFee: float  # Delivery fee (may be paid separately in cash)
    includesDeliveryFee: bool = True  # False if delivery is paid separately in cash
    taxAmount: float = 0.0  # Future: taxes
    discountAmount: float = 0.0  # Future: discounts
    commissionAmount: float  # Commission charged to customer
    totalAmount: float  # Final amount to pay
    currency: str  # "usd" or "local" (cup)

    # Status
    status: PaymentAttemptStatus = PaymentAttemptStatus.PENDING

    # Stripe-specific fields
    stripePaymentIntentId: Optional[str] = None
    stripeClientSecret: Optional[str] = None

    # Manual payment fields (transfers, etc.)
    sendsSmsNotification: bool = False  # User indicated their transfer will send an SMS (Transfermóvil, etc.)
    proofUrl: Optional[str] = None  # Receipt/proof uploaded by customer
    customerConfirmedAt: Optional[datetime] = None
    businessConfirmedAt: Optional[datetime] = None
    disputeReason: Optional[str] = None

    # Cash payment fields
    deliveryPersonConfirmedAt: Optional[datetime] = None
    deliveryPersonId: Optional[PyObjectId] = None

    # Wallet transaction reference
    walletTransactionId: Optional[str] = None  # For wallet payments
    businessWalletTransactionId: Optional[str] = None  # Credit to business
    commissionTransactionId: Optional[str] = None  # Commission to platform

    # Refund fields
    refundRequestedAt: Optional[datetime] = None
    refundReason: Optional[str] = None
    refundedAt: Optional[datetime] = None
    refundTransactionId: Optional[str] = None
    refundAmount: Optional[float] = None

    # Lifecycle timestamps
    expiresAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    failedAt: Optional[datetime] = None
    failedReason: Optional[str] = None

    # Audit
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True


class RefundRequest(BaseModel):
    """
    Refund request model.

    Used to track refund requests separately from the payment attempt.
    """

    id: PyObjectId = Field(alias="_id")
    paymentAttemptId: PyObjectId
    orderId: PyObjectId
    customerId: PyObjectId
    amount: float
    currency: str
    reason: str
    status: str = "pending"  # "pending", "approved", "rejected", "completed"

    # Processing
    approvedBy: Optional[PyObjectId] = None
    approvedAt: Optional[datetime] = None
    rejectedReason: Optional[str] = None
    completedAt: Optional[datetime] = None
    transactionId: Optional[str] = None

    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
