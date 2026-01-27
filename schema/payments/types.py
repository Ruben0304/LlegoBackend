"""GraphQL type definitions for Payment entity."""
import strawberry
from typing import Optional
from datetime import datetime
from enum import Enum


@strawberry.enum
class PaymentAttemptStatusEnum(Enum):
    """Status of a payment attempt."""
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_PROOF = "awaiting_proof"
    AWAITING_BUSINESS = "awaiting_business"
    AWAITING_DELIVERY = "awaiting_delivery"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    REFUND_REQUESTED = "refund_requested"
    REFUND_PROCESSING = "refund_processing"
    REFUNDED = "refunded"


@strawberry.type
class PaymentType:
    """Tipo GraphQL para pagos procesados mediante OCR de SMS bancarios."""
    id: str
    quien_envio: str
    banco: str
    fecha: datetime
    es_mensaje_banco: bool
    cantidad_transferida: float
    numero_transferencia: str
    primeros_4_tarjeta: str
    ultimos_4_tarjeta: str
    createdAt: datetime


@strawberry.type
class PaymentMethodType:
    """Payment method configuration."""
    id: str = strawberry.field(description="Payment method ID")
    name: str = strawberry.field(description="Display name")
    code: str = strawberry.field(description="Internal code")
    currency: str = strawberry.field(description="Currency code")
    method: str = strawberry.field(description="Method type")
    commissionPercent: float = strawberry.field(description="Commission percentage charged")
    deliveryFeePercent: float = strawberry.field(description="Delivery fee percentage")
    isRefundable: bool = strawberry.field(description="Whether refunds are allowed")
    requiresProof: bool = strawberry.field(description="Whether proof is required")
    requiresBusinessConfirmation: bool = strawberry.field(description="Whether business confirmation is required")
    expirationMinutes: Optional[int] = strawberry.field(description="Expiration in minutes", default=None)
    isActive: bool = strawberry.field(description="Whether method is active")
    displayOrder: int = strawberry.field(description="Display order")
    iconUrl: Optional[str] = strawberry.field(description="Icon URL", default=None)
    instructions: Optional[str] = strawberry.field(description="Payment instructions", default=None)
    createdAt: datetime = strawberry.field(description="Creation time")
    updatedAt: datetime = strawberry.field(description="Last update time")


@strawberry.type
class PaymentAttemptType:
    """Payment attempt for an order."""
    id: str = strawberry.field(description="Payment attempt ID")
    orderId: str = strawberry.field(description="Order ID")
    paymentMethodId: str = strawberry.field(description="Payment method ID")

    # Amounts
    subtotal: float = strawberry.field(description="Order subtotal")
    deliveryFee: float = strawberry.field(description="Delivery fee")
    includesDeliveryFee: bool = strawberry.field(description="Whether delivery is included")
    taxAmount: float = strawberry.field(description="Tax amount")
    discountAmount: float = strawberry.field(description="Discount amount")
    commissionAmount: float = strawberry.field(description="Commission charged")
    totalAmount: float = strawberry.field(description="Total to pay")
    currency: str = strawberry.field(description="Currency (usd or local)")

    # Status
    status: PaymentAttemptStatusEnum = strawberry.field(description="Current status")

    # Stripe fields
    stripePaymentIntentId: Optional[str] = strawberry.field(description="Stripe Payment Intent ID")
    stripeClientSecret: Optional[str] = strawberry.field(description="Stripe client secret for UI")

    # Manual payment fields
    proofUrl: Optional[str] = strawberry.field(description="Proof/receipt URL")
    customerConfirmedAt: Optional[datetime] = strawberry.field(description="When customer confirmed")
    businessConfirmedAt: Optional[datetime] = strawberry.field(description="When business confirmed")
    disputeReason: Optional[str] = strawberry.field(description="Dispute reason if disputed")

    # Cash payment fields
    deliveryPersonConfirmedAt: Optional[datetime] = strawberry.field(description="When delivery confirmed cash")
    deliveryPersonId: Optional[str] = strawberry.field(description="Delivery person who confirmed")

    # Wallet transaction references
    walletTransactionId: Optional[str] = strawberry.field(description="User wallet transaction ID")
    businessWalletTransactionId: Optional[str] = strawberry.field(description="Business wallet transaction ID")
    commissionTransactionId: Optional[str] = strawberry.field(description="Commission transaction ID")

    # Refund fields
    refundRequestedAt: Optional[datetime] = strawberry.field(description="When refund was requested")
    refundReason: Optional[str] = strawberry.field(description="Refund reason")
    refundedAt: Optional[datetime] = strawberry.field(description="When refund completed")
    refundTransactionId: Optional[str] = strawberry.field(description="Refund transaction ID")
    refundAmount: Optional[float] = strawberry.field(description="Refund amount")

    # Lifecycle
    expiresAt: Optional[datetime] = strawberry.field(description="Expiration time")
    completedAt: Optional[datetime] = strawberry.field(description="Completion time")
    failedAt: Optional[datetime] = strawberry.field(description="Failure time")
    failedReason: Optional[str] = strawberry.field(description="Failure reason")

    # Timestamps
    createdAt: datetime = strawberry.field(description="Creation time")
    updatedAt: datetime = strawberry.field(description="Last update time")


@strawberry.type
class InitiatePaymentResult:
    """Result of initiating a payment."""
    paymentAttempt: PaymentAttemptType = strawberry.field(description="The created payment attempt")
    instructions: Optional[str] = strawberry.field(
        description="Instructions for completing payment (for manual methods)"
    )


@strawberry.type
class PlatformWalletType:
    """Platform wallet balance."""
    local: float = strawberry.field(description="CUP balance")
    usd: float = strawberry.field(description="USD balance")


@strawberry.type
class PlatformType:
    """Platform information."""
    id: str = strawberry.field(description="Platform ID")
    name: str = strawberry.field(description="Platform name")
    wallet: PlatformWalletType = strawberry.field(description="Platform wallet")
    totalCommissionsCollected: float = strawberry.field(description="Total commissions collected")
    totalOrdersProcessed: int = strawberry.field(description="Total orders processed")


def payment_attempt_to_type(attempt) -> PaymentAttemptType:
    """Convert PaymentAttempt model to GraphQL type."""
    return PaymentAttemptType(
        id=attempt.id,
        orderId=attempt.orderId,
        paymentMethodId=attempt.paymentMethodId,
        subtotal=attempt.subtotal,
        deliveryFee=attempt.deliveryFee,
        includesDeliveryFee=attempt.includesDeliveryFee,
        taxAmount=attempt.taxAmount,
        discountAmount=attempt.discountAmount,
        commissionAmount=attempt.commissionAmount,
        totalAmount=attempt.totalAmount,
        currency=attempt.currency,
        status=PaymentAttemptStatusEnum(attempt.status),
        stripePaymentIntentId=attempt.stripePaymentIntentId,
        stripeClientSecret=attempt.stripeClientSecret,
        proofUrl=attempt.proofUrl,
        customerConfirmedAt=attempt.customerConfirmedAt,
        businessConfirmedAt=attempt.businessConfirmedAt,
        disputeReason=attempt.disputeReason,
        deliveryPersonConfirmedAt=attempt.deliveryPersonConfirmedAt,
        deliveryPersonId=attempt.deliveryPersonId,
        walletTransactionId=attempt.walletTransactionId,
        businessWalletTransactionId=attempt.businessWalletTransactionId,
        commissionTransactionId=attempt.commissionTransactionId,
        refundRequestedAt=attempt.refundRequestedAt,
        refundReason=attempt.refundReason,
        refundedAt=attempt.refundedAt,
        refundTransactionId=attempt.refundTransactionId,
        refundAmount=attempt.refundAmount,
        expiresAt=attempt.expiresAt,
        completedAt=attempt.completedAt,
        failedAt=attempt.failedAt,
        failedReason=attempt.failedReason,
        createdAt=attempt.createdAt,
        updatedAt=attempt.updatedAt,
    )
