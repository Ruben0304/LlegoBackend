"""Payment service for handling payment processing logic."""

import logging
import mimetypes
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import stripe
from bson import ObjectId

from clients.mongodb_client import get_database
from clients.s3_client import get_s3_client
from core.config import settings
from domain.payments import PaymentAttempt, PaymentAttemptStatus
from repositories import (
    branches_repo,
    businesses_repo,
    users_repo,
)
from repositories.payments_attempt_repository import PaymentAttemptRepository
from services.shortcut_transfer_service import shortcut_transfer_service

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key


class PaymentService:
    """Service for payment processing business logic."""

    def __init__(self):
        self.payment_attempts_repo = PaymentAttemptRepository()

    @staticmethod
    def _get_kyc_dependencies():
        """Lazy-load KYC modules to avoid hard startup dependency."""
        from repositories.kyc_audit_event_repository import kyc_audit_events_repo
        from repositories.kyc_verification_repository import kyc_verifications_repo
        from services.kyc.kyc_decision_service import kyc_decision_service
        from services.kyc.kyc_notification_service import kyc_notification_service

        return (
            kyc_decision_service,
            kyc_verifications_repo,
            kyc_audit_events_repo,
            kyc_notification_service,
        )

    @staticmethod
    def _to_object_id(value: Optional[str]):
        if value is None:
            return None
        try:
            return ObjectId(value)
        except Exception:
            return value

    async def _get_order(self, order_id: str):
        """Get order by ID."""
        db = get_database()
        try:
            doc = await db.orders.find_one({"_id": ObjectId(order_id)})
        except Exception:
            doc = await db.orders.find_one({"_id": order_id})
        return doc

    async def _get_payment_method(self, payment_method_id: str):
        """Get payment method by ID."""
        db = get_database()
        try:
            doc = await db.payment_methods.find_one(
                {"_id": ObjectId(payment_method_id)}
            )
        except Exception:
            doc = await db.payment_methods.find_one({"_id": payment_method_id})
        return doc

    async def _get_branch(self, branch_id: str):
        """Get branch by ID using the branch repository."""
        branch = await branches_repo.get_by_id(branch_id)
        return branch.model_dump() if branch else None

    async def _resolve_cash_kyc_policy_context(
        self,
        *,
        merchant_id: str,
        branch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve branch-scoped cash KYC policy for a merchant."""
        branch_doc = None
        if branch_id:
            branch_doc = await self._get_branch(branch_id)
            if not branch_doc:
                raise ValueError("Sucursal no encontrada")
            if str(branch_doc.get("businessId")) != merchant_id:
                raise ValueError("Sucursal no pertenece al merchant indicado")
        else:
            branches = await branches_repo.get_by_business(merchant_id)
            if branches:
                # Keep deterministic behavior for profile flow when branch is omitted.
                branch_doc = branches[0].model_dump()

        branch_doc = branch_doc or {}
        required = bool(
            settings.cash_kyc_feature_enabled
            and branch_doc.get("cashKycEnabled", False)
        )
        return {
            "merchantId": merchant_id,
            "branchId": str(branch_doc.get("_id") or branch_doc.get("id"))
            if branch_doc
            else None,
            "required": required,
            "policyVersion": branch_doc.get("cashKycPolicyVersion", "cash-kyc-v1"),
            "minConfidence": float(
                branch_doc.get(
                    "cashKycMinConfidence", settings.cash_kyc_default_min_confidence
                )
            ),
            "ttlDays": int(
                branch_doc.get("cashKycTtlDays", settings.cash_kyc_default_ttl_days)
            ),
            "branchDoc": branch_doc,
        }

    async def _get_user(self, user_id: str):
        """Get user by ID using the user repository."""
        user = await users_repo.get_by_id(user_id)
        return user.model_dump() if user else None

    async def _get_platform(self):
        """Get or create platform document."""
        db = get_database()
        doc = await db.platform.find_one({"_id": "platform"})
        if not doc:
            doc = {
                "_id": "platform",
                "name": "Llego",
                "wallet": {"local": 0.0, "usd": 0.0},
                "walletStatus": "active",
                "totalCommissionsCollected": 0.0,
                "totalOrdersProcessed": 0,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            await db.platform.insert_one(doc)
        return doc

    def _calculate_amounts(
        self, order: dict, payment_method: dict, include_delivery: bool = True
    ) -> Tuple[float, float, float, float, str]:
        """
        Calculate payment amounts.

        Returns:
            Tuple of (subtotal, delivery_fee, commission, total, currency)
        """
        subtotal = float(order.get("subtotal", 0))
        delivery_fee = float(order.get("deliveryFee", 0)) if include_delivery else 0.0

        # Determine currency based on payment method
        pm_currency = payment_method.get("currency", "USD").upper()
        currency = "usd" if pm_currency == "USD" else "local"

        # Calculate commission
        commission_percent = float(payment_method.get("commissionPercent", 0))

        # For cash payments with delivery, add delivery fee percentage
        if payment_method.get("method") == "cash" and include_delivery:
            delivery_fee_percent = float(payment_method.get("deliveryFeePercent", 0))
            # Apply delivery fee percentage to delivery fee
            delivery_fee = delivery_fee * (1 + delivery_fee_percent / 100)

        # Calculate base for commission (subtotal + delivery if applicable)
        base_amount = subtotal + delivery_fee
        commission = round(base_amount * (commission_percent / 100), 2)

        total = round(subtotal + delivery_fee + commission, 2)

        return subtotal, delivery_fee, commission, total, currency

    async def initiate_payment(
        self,
        order_id: str,
        payment_method_id: str,
        user_id: str,
        include_delivery_fee: bool = True,
        sends_sms_notification: bool = False,
    ) -> PaymentAttempt:
        """
        Initiate a payment for an order.

        This creates a PaymentAttempt and handles the initial processing
        based on the payment method type.

        Args:
            order_id: The order to pay for
            payment_method_id: The payment method to use
            user_id: The user initiating the payment
            include_delivery_fee: Whether to include delivery in this payment

        Returns:
            PaymentAttempt with appropriate status and fields
        """
        # Get order
        order = await self._get_order(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify user owns the order
        if order.get("customerId") != user_id:
            raise ValueError("No autorizado para pagar este pedido")

        # Check order status - must be in a payable state
        # Solo permitir pago después de que negocio acepte
        payable_statuses = ["pending_payment", "accepted", "modified_by_store"]
        if order.get("status") not in payable_statuses:
            raise ValueError(
                f"El pedido no está en un estado que permita pago: {order.get('status')}"
            )

        # Check if there's already an active payment attempt
        existing = await self.payment_attempts_repo.get_active_by_order_id(order_id)
        if existing:
            raise ValueError("Ya existe un intento de pago activo para este pedido")

        # Get payment method
        payment_method = await self._get_payment_method(payment_method_id)
        if not payment_method:
            raise ValueError("Método de pago no encontrado")

        if not payment_method.get("isActive", True):
            raise ValueError("Método de pago no disponible")

        # Calculate amounts
        subtotal, delivery_fee, commission, total, currency = self._calculate_amounts(
            order, payment_method, include_delivery_fee
        )

        # Create payment attempt
        attempt_id = str(ObjectId())
        expires_at = None
        if payment_method.get("expirationMinutes"):
            expires_at = datetime.utcnow() + timedelta(
                minutes=payment_method["expirationMinutes"]
            )

        payment_attempt = PaymentAttempt(
            _id=attempt_id,
            orderId=order_id,
            paymentMethodId=payment_method_id,
            subtotal=subtotal,
            deliveryFee=delivery_fee,
            includesDeliveryFee=include_delivery_fee,
            taxAmount=0.0,  # Future
            discountAmount=0.0,  # Future
            commissionAmount=commission,
            totalAmount=total,
            currency=currency,
            status=PaymentAttemptStatus.PENDING,
            expiresAt=expires_at,
            sendsSmsNotification=sends_sms_notification,
        )

        # Handle based on payment method type
        method_type = payment_method.get("method", "").lower()

        if method_type == "wallet":
            # Process wallet payment immediately
            payment_attempt = await self._process_wallet_payment(
                payment_attempt, order, payment_method, user_id
            )

        elif method_type == "stripe":
            # Create Stripe Payment Intent
            payment_attempt = await self._create_stripe_payment_intent(
                payment_attempt, order, payment_method, user_id
            )

        elif method_type == "transfer":
            # Manual transfer - wait for proof
            payment_attempt.status = PaymentAttemptStatus.AWAITING_PROOF

        elif method_type == "cash":
            payment_attempt = await self._apply_cash_kyc_policy(
                payment_attempt=payment_attempt,
                order=order,
                user_id=user_id,
            )

        else:
            raise ValueError(f"Método de pago no soportado: {method_type}")

        # Save payment attempt
        await self.payment_attempts_repo.create(payment_attempt)

        # Update order with current payment attempt
        await self._update_order_payment_attempt(order_id, attempt_id)

        return payment_attempt

    async def _apply_cash_kyc_policy(
        self,
        *,
        payment_attempt: PaymentAttempt,
        order: dict,
        user_id: str,
    ) -> PaymentAttempt:
        """Apply cash KYC policy with safe defaults and backward compatibility."""
        kyc_decision_service, _, _, _ = self._get_kyc_dependencies()
        branch = await self._get_branch(order.get("branchId"))
        if not settings.cash_kyc_feature_enabled:
            payment_attempt.status = PaymentAttemptStatus.AWAITING_DELIVERY
            payment_attempt.kycRequired = False
            payment_attempt.kycEvalStatus = "not_required"
            payment_attempt.cashCoverageStatus = "eligible_uncovered"
            return payment_attempt

        cash_kyc_enabled = bool((branch or {}).get("cashKycEnabled", False))
        policy_version = (branch or {}).get("cashKycPolicyVersion", "cash-kyc-v1")

        if not cash_kyc_enabled:
            payment_attempt.status = PaymentAttemptStatus.AWAITING_DELIVERY
            payment_attempt.kycRequired = False
            payment_attempt.kycEvalStatus = "not_required"
            payment_attempt.cashCoverageStatus = "eligible_uncovered"
            return payment_attempt

        global_approved = await kyc_decision_service.get_global_approved(
            customer_id=user_id
        )
        if global_approved:
            payment_attempt.status = PaymentAttemptStatus.AWAITING_DELIVERY
            payment_attempt.kycRequired = True
            payment_attempt.kycEvalStatus = "approved"
            payment_attempt.cashCoverageStatus = "eligible_covered"
            payment_attempt.latestKycVerificationId = global_approved.id
            payment_attempt.kycDecisionAt = datetime.utcnow()
            return payment_attempt

        payment_attempt.status = PaymentAttemptStatus.AWAITING_KYC
        payment_attempt.kycRequired = True
        payment_attempt.kycEvalStatus = "pending_evidence"
        payment_attempt.cashCoverageStatus = "blocked"
        payment_attempt.kycDecisionAt = datetime.utcnow()
        return payment_attempt

    async def get_cash_kyc_policy(self, order_id: str, user_id: str) -> dict:
        """Return cash KYC policy for a given order and authenticated customer."""
        order = await self._get_order(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        if order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        branch = await self._get_branch(order.get("branchId")) or {}
        required = bool(
            settings.cash_kyc_feature_enabled and branch.get("cashKycEnabled", False)
        )
        min_conf = float(
            branch.get("cashKycMinConfidence", settings.cash_kyc_default_min_confidence)
        )
        ttl_days = int(branch.get("cashKycTtlDays", settings.cash_kyc_default_ttl_days))
        policy_version = branch.get("cashKycPolicyVersion", "cash-kyc-v1")

        return {
            "kycRequired": required,
            "policyVersion": policy_version,
            "minConfidence": min_conf,
            "ttlDays": ttl_days,
            "allowCashNow": not required,
            "appCoversCashNow": False,
        }

    @staticmethod
    def _normalize_s3_key(ref: str) -> str:
        if ref.startswith("s3://"):
            without_scheme = ref[len("s3://") :]
            if "/" in without_scheme:
                return without_scheme.split("/", 1)[1]
            return without_scheme
        return ref.lstrip("/")

    @staticmethod
    def _guess_mime_from_ref(ref: str) -> str:
        guessed, _ = mimetypes.guess_type(ref)
        return guessed or "image/jpeg"

    def _load_s3_bytes_from_ref(self, ref: str) -> bytes:
        key = self._normalize_s3_key(ref)
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
        body = obj.get("Body")
        return body.read() if body else b""

    async def get_cash_kyc_policy_by_merchant(
        self,
        *,
        merchant_id: str,
        user_id: str,
        branch_id: Optional[str] = None,
    ) -> dict:
        """Return cash KYC policy for a merchant/branch without requiring an order."""
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")

        business = await businesses_repo.get_by_id(merchant_id)
        if not business:
            raise ValueError("Merchant no encontrado")

        ctx = await self._resolve_cash_kyc_policy_context(
            merchant_id=merchant_id, branch_id=branch_id
        )
        return {
            "kycRequired": ctx["required"],
            "policyVersion": ctx["policyVersion"],
            "minConfidence": ctx["minConfidence"],
            "ttlDays": ctx["ttlDays"],
            "allowCashNow": not ctx["required"],
            "appCoversCashNow": False,
        }

    async def get_cash_kyc_status(self, payment_attempt_id: str, user_id: str) -> dict:
        """Get KYC status and effective cash/covers flags for an attempt."""
        _, kyc_verifications_repo, _, _ = self._get_kyc_dependencies()
        attempt = await self.get_payment_attempt(payment_attempt_id, user_id)
        verification = None
        if attempt.latestKycVerificationId:
            verification = await kyc_verifications_repo.get_by_id(
                str(attempt.latestKycVerificationId)
            )

        allow_cash = attempt.cashCoverageStatus in {
            "eligible_covered",
            "eligible_uncovered",
        }
        app_covers = attempt.cashCoverageStatus == "eligible_covered"
        return {
            "paymentAttemptId": str(attempt.id),
            "verificationId": str(attempt.latestKycVerificationId)
            if attempt.latestKycVerificationId
            else None,
            "kycEvalStatus": attempt.kycEvalStatus,
            "cashCoverageStatus": attempt.cashCoverageStatus,
            "allowCash": allow_cash,
            "appCoversCash": app_covers,
            "reasonCodes": verification.reasonCodes if verification else [],
            "nextAction": "continue_cash_flow" if allow_cash else "start_kyc",
            "expiresAt": verification.expiresAt if verification else None,
        }

    async def get_cash_kyc_status_by_account(
        self,
        *,
        merchant_id: str,
        user_id: str,
        branch_id: Optional[str] = None,
    ) -> dict:
        """Get KYC status for a user scoped by merchant, independent from checkout."""
        _, kyc_verifications_repo, _, _ = self._get_kyc_dependencies()
        global_approved = await kyc_verifications_repo.get_global_approved(
            customer_id=user_id,
        )
        if global_approved:
            return {
                "merchantId": merchant_id,
                "branchId": branch_id,
                "verificationId": str(global_approved.id),
                "kycEvalStatus": "approved",
                "cashCoverageStatus": "eligible_covered",
                "allowCash": True,
                "appCoversCash": True,
                "reasonCodes": global_approved.reasonCodes or [],
                "nextAction": "continue_cash_flow",
                "expiresAt": global_approved.expiresAt,
            }

        latest = await kyc_verifications_repo.get_latest_global_by_customer(
            customer_id=user_id,
        )
        latest_status = latest.status if latest else "pending_evidence"
        return {
            "merchantId": merchant_id,
            "branchId": branch_id,
            "verificationId": str(latest.id) if latest else None,
            "kycEvalStatus": latest_status,
            "cashCoverageStatus": "blocked",
            "allowCash": False,
            "appCoversCash": False,
            "reasonCodes": latest.reasonCodes if latest else [],
            "nextAction": "start_kyc" if not latest else "retry_or_provide_evidence",
            "expiresAt": latest.expiresAt if latest else None,
        }

    async def get_global_cash_kyc_status(self, *, user_id: str) -> dict:
        """Get global account KYC status (merchant-independent)."""
        _, kyc_verifications_repo, _, _ = self._get_kyc_dependencies()
        global_approved = await kyc_verifications_repo.get_global_approved(
            customer_id=user_id
        )
        if global_approved:
            return {
                "verificationId": str(global_approved.id),
                "kycEvalStatus": "approved",
                "cashCoverageStatus": "eligible_covered",
                "allowCash": True,
                "appCoversCash": True,
                "reasonCodes": global_approved.reasonCodes or [],
                "nextAction": "continue_cash_flow",
                "expiresAt": global_approved.expiresAt,
            }

        latest = await kyc_verifications_repo.get_latest_global_by_customer(
            customer_id=user_id
        )
        latest_status = latest.status if latest else "pending_evidence"
        return {
            "verificationId": str(latest.id) if latest else None,
            "kycEvalStatus": latest_status,
            "cashCoverageStatus": "blocked",
            "allowCash": False,
            "appCoversCash": False,
            "reasonCodes": latest.reasonCodes if latest else [],
            "nextAction": "start_kyc" if not latest else "retry_or_provide_evidence",
            "expiresAt": latest.expiresAt if latest else None,
        }

    async def start_cash_kyc_evaluation(
        self,
        *,
        payment_attempt_id: str,
        user_id: str,
        identity_document_front_ref: str,
        selfie_live_ref: str,
        device_context: dict,
    ) -> dict:
        """Start KYC evaluation for a cash payment attempt."""
        (
            kyc_decision_service,
            _kyc_verifications_repo,
            kyc_audit_events_repo,
            kyc_notification_service,
        ) = self._get_kyc_dependencies()
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")
        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")
        if attempt.status not in {
            PaymentAttemptStatus.AWAITING_KYC,
            PaymentAttemptStatus.AWAITING_DELIVERY,
        }:
            raise ValueError(f"Estado no válido para KYC: {attempt.status}")

        branch = await self._get_branch(order.get("branchId")) or {}
        if not bool(branch.get("cashKycEnabled", False)):
            return {
                "verificationId": "",
                "kycEvalStatus": "not_required",
                "cashCoverageStatus": "eligible_uncovered",
                "allowCash": True,
                "appCoversCash": False,
                "nextAction": "continue_cash_uncovered",
                "correlationId": "",
                "reasonCodes": [],
            }

        evidence_refs = [
            {"type": "identity_document_front", "ref": identity_document_front_ref},
            {"type": "selfie_live", "ref": selfie_live_ref},
        ]

        identity_document_front_bytes = self._load_s3_bytes_from_ref(
            identity_document_front_ref
        )
        selfie_with_id_bytes = self._load_s3_bytes_from_ref(selfie_live_ref)
        if not identity_document_front_bytes or not selfie_with_id_bytes:
            raise ValueError("EVIDENCE_NOT_FOUND")

        result = await kyc_decision_service.evaluate_global_cash_kyc_with_images(
            customer_id=user_id,
            policy_version=settings.cash_kyc_global_policy_version,
            min_confidence=settings.cash_kyc_default_min_confidence,
            ttl_days=settings.cash_kyc_default_ttl_days,
            evidence_refs=evidence_refs,
            device_context=device_context,
            selfie_with_id_bytes=selfie_with_id_bytes,
            selfie_with_id_mime_type=self._guess_mime_from_ref(selfie_live_ref),
            identity_document_front_bytes=identity_document_front_bytes,
            identity_document_front_mime_type=self._guess_mime_from_ref(
                identity_document_front_ref
            ),
        )

        new_attempt_status = (
            PaymentAttemptStatus.AWAITING_DELIVERY
            if result["kyc_eval_status"] == "approved"
            else PaymentAttemptStatus.AWAITING_KYC
        )
        await self.payment_attempts_repo.update_status(
            payment_attempt_id,
            new_attempt_status,
        )
        await self.payment_attempts_repo.update_kyc_state(
            payment_attempt_id,
            kyc_required=True,
            kyc_eval_status=result["kyc_eval_status"],
            cash_coverage_status=result["cash_coverage_status"],
            latest_kyc_verification_id=result["verification_id"],
            kyc_failure_code=result.get("provider_error"),
        )

        await kyc_audit_events_repo.append(
            entity_type="kyc_verification",
            entity_id=result["verification_id"],
            event_type="kyc_evaluated",
            actor_type="customer",
            actor_id=user_id,
            payload={
                "kycEvalStatus": result["kyc_eval_status"],
                "cashCoverageStatus": result["cash_coverage_status"],
            },
        )

        await kyc_notification_service.notify_merchant(
            kyc_verification_id=result["verification_id"],
            branch_id=str(order.get("branchId")),
            event_type="kyc_evaluated",
            title="Actualización KYC pago en efectivo",
            body=f"Estado KYC: {result['kyc_eval_status']}",
            data={
                "type": "cash_kyc_status",
                "payment_attempt_id": str(attempt.id),
                "verification_id": result["verification_id"],
                "kyc_eval_status": result["kyc_eval_status"],
            },
        )

        return {
            "verificationId": result["verification_id"],
            "kycEvalStatus": result["kyc_eval_status"],
            "cashCoverageStatus": result["cash_coverage_status"],
            "allowCash": result["cash_coverage_status"]
            in {"eligible_covered", "eligible_uncovered"},
            "appCoversCash": result["cash_coverage_status"] == "eligible_covered",
            "nextAction": result["next_action"],
            "correlationId": result["correlation_id"],
            "reasonCodes": result.get("reason_codes", []),
            "providerError": result.get("provider_error"),
            "providerErrorCode": result.get("error_code"),
        }

    async def start_cash_kyc_evaluation_by_account(
        self,
        *,
        merchant_id: str,
        user_id: str,
        branch_id: Optional[str],
        identity_document_front_ref: str,
        selfie_live_ref: str,
        device_context: dict,
    ) -> dict:
        """Start KYC evaluation from account/profile flow without payment attempt."""
        (
            kyc_decision_service,
            _kyc_verifications_repo,
            kyc_audit_events_repo,
            _kyc_notification_service,
        ) = self._get_kyc_dependencies()

        evidence_refs = [
            {"type": "identity_document_front", "ref": identity_document_front_ref},
            {"type": "selfie_live", "ref": selfie_live_ref},
        ]

        identity_document_front_bytes = self._load_s3_bytes_from_ref(
            identity_document_front_ref
        )
        selfie_with_id_bytes = self._load_s3_bytes_from_ref(selfie_live_ref)
        if not identity_document_front_bytes or not selfie_with_id_bytes:
            raise ValueError("EVIDENCE_NOT_FOUND")

        result = await kyc_decision_service.evaluate_global_cash_kyc_with_images(
            customer_id=user_id,
            policy_version=settings.cash_kyc_global_policy_version,
            min_confidence=settings.cash_kyc_default_min_confidence,
            ttl_days=settings.cash_kyc_default_ttl_days,
            evidence_refs=evidence_refs,
            device_context=device_context,
            selfie_with_id_bytes=selfie_with_id_bytes,
            selfie_with_id_mime_type=self._guess_mime_from_ref(selfie_live_ref),
            identity_document_front_bytes=identity_document_front_bytes,
            identity_document_front_mime_type=self._guess_mime_from_ref(
                identity_document_front_ref
            ),
        )

        await kyc_audit_events_repo.append(
            entity_type="kyc_verification",
            entity_id=result["verification_id"],
            event_type="kyc_evaluated",
            actor_type="customer",
            actor_id=user_id,
            payload={
                "source": "global_account",
                "merchantId": merchant_id,
                "branchId": branch_id,
                "kycEvalStatus": result["kyc_eval_status"],
                "cashCoverageStatus": result["cash_coverage_status"],
            },
        )

        return {
            "verificationId": result["verification_id"],
            "kycEvalStatus": result["kyc_eval_status"],
            "cashCoverageStatus": result["cash_coverage_status"],
            "allowCash": result["cash_coverage_status"]
            in {"eligible_covered", "eligible_uncovered"},
            "appCoversCash": result["cash_coverage_status"] == "eligible_covered",
            "nextAction": result["next_action"],
            "correlationId": result["correlation_id"],
            "reasonCodes": result.get("reason_codes", []),
            "providerError": result.get("provider_error"),
            "providerErrorCode": result.get("error_code"),
        }

    async def start_global_cash_kyc_evaluation(
        self,
        *,
        user_id: str,
        identity_document_front_ref: str,
        selfie_with_id_ref: str,
        device_context: dict,
    ) -> dict:
        """Merchant-independent global account KYC evaluation."""
        return await self.start_cash_kyc_evaluation_by_account(
            merchant_id="global",
            user_id=user_id,
            branch_id=None,
            identity_document_front_ref=identity_document_front_ref,
            selfie_live_ref=selfie_with_id_ref,
            device_context=device_context,
        )

    async def retry_cash_kyc_evaluation(
        self, verification_id: str, user_id: str
    ) -> dict:
        _, kyc_verifications_repo, _, _ = self._get_kyc_dependencies()
        verification = await kyc_verifications_repo.get_by_id(verification_id)
        if not verification:
            raise ValueError("Verificación KYC no encontrada")
        if not verification.paymentAttemptId:
            raise ValueError("RETRY_NOT_SUPPORTED_FOR_ACCOUNT_VERIFICATION")
        attempt = await self.payment_attempts_repo.get_by_id(
            str(verification.paymentAttemptId)
        )
        if not attempt:
            raise ValueError("Intento de pago no encontrado")
        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if verification.retryCount >= settings.cash_kyc_max_auto_retries:
            raise ValueError("MAX_RETRIES_REACHED")

        await kyc_verifications_repo.increment_retry(verification_id, "MANUAL_RETRY")
        if not verification.evidenceRefs or len(verification.evidenceRefs) < 2:
            raise ValueError("EVIDENCE_MISSING")
        identity_ref = None
        selfie_ref = None
        for item in verification.evidenceRefs:
            if item.get("type") == "identity_document_front":
                identity_ref = item.get("ref")
            elif item.get("type") == "selfie_live":
                selfie_ref = item.get("ref")
        if not identity_ref or not selfie_ref:
            raise ValueError("EVIDENCE_MISSING")

        return await self.start_cash_kyc_evaluation(
            payment_attempt_id=str(attempt.id),
            user_id=user_id,
            identity_document_front_ref=identity_ref,
            selfie_live_ref=selfie_ref,
            device_context={},
        )

    async def override_cash_kyc_decision(
        self,
        *,
        verification_id: str,
        actor_id: str,
        actor_role: str,
        decision: str,
        reason: str,
    ) -> dict:
        _, kyc_verifications_repo, kyc_audit_events_repo, _ = (
            self._get_kyc_dependencies()
        )
        if actor_role not in {"admin", "risk_admin"}:
            raise ValueError("No autorizado para override KYC")

        verification = await kyc_verifications_repo.get_by_id(verification_id)
        if not verification:
            raise ValueError("Verificación KYC no encontrada")

        if decision == "force_reevaluation":
            await kyc_verifications_repo.increment_retry(
                verification_id, "FORCE_REEVALUATION"
            )
            return {
                "verificationId": verification_id,
                "kycEvalStatus": "submitted",
                "cashCoverageStatus": "blocked",
                "allowCash": False,
                "appCoversCash": False,
                "reason": reason,
            }

        status_map = {
            "approve": ("approved", "eligible_covered"),
            "reject": ("rejected", "blocked"),
        }
        if decision not in status_map:
            raise ValueError("Decisión inválida")

        kyc_status, coverage_status = status_map[decision]
        expires_at = (
            datetime.utcnow() + timedelta(days=settings.cash_kyc_default_ttl_days)
            if decision == "approve"
            else None
        )
        await kyc_verifications_repo.update_result(
            verification_id=verification_id,
            status=kyc_status,
            verdict="valid" if decision == "approve" else "invalid",
            confidence_score=1.0 if decision == "approve" else 0.0,
            reason_codes=["MANUAL_OVERRIDE"],
            extracted_signals={"reason": reason},
            model_version="manual_override",
            evaluated_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        if verification.paymentAttemptId:
            await self.payment_attempts_repo.update_kyc_state(
                str(verification.paymentAttemptId),
                kyc_required=True,
                kyc_eval_status=kyc_status,
                cash_coverage_status=coverage_status,
                latest_kyc_verification_id=verification_id,
            )
            await self.payment_attempts_repo.update_status(
                str(verification.paymentAttemptId),
                PaymentAttemptStatus.AWAITING_DELIVERY
                if decision == "approve"
                else PaymentAttemptStatus.AWAITING_KYC,
            )
        await kyc_audit_events_repo.append(
            entity_type="kyc_verification",
            entity_id=verification_id,
            event_type="kyc_override",
            actor_type=actor_role,
            actor_id=actor_id,
            payload={"decision": decision, "reason": reason},
        )
        return {
            "verificationId": verification_id,
            "kycEvalStatus": kyc_status,
            "cashCoverageStatus": coverage_status,
            "allowCash": coverage_status in {"eligible_covered", "eligible_uncovered"},
            "appCoversCash": coverage_status == "eligible_covered",
            "reason": reason,
        }

    async def _process_wallet_payment(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str,
    ) -> PaymentAttempt:
        """Process an immediate wallet payment."""
        db = get_database()

        # Get user and verify balance
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("Usuario no encontrado")

        user_wallet = user.get("wallet", {"local": 0, "usd": 0})
        currency = payment_attempt.currency
        user_balance = float(user_wallet.get(currency, 0))

        if user_balance < payment_attempt.totalAmount:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = "Saldo insuficiente"
            return payment_attempt

        # Get branch
        branch = await self._get_branch(order.get("branchId"))
        if not branch:
            raise ValueError("Sucursal no encontrada")

        # Get platform
        platform = await self._get_platform()

        # Calculate amounts
        amount_to_business = payment_attempt.subtotal + payment_attempt.deliveryFee
        commission = payment_attempt.commissionAmount

        # Atomic debit from user wallet
        try:
            user_id_obj = ObjectId(user_id)
        except Exception:
            user_id_obj = user_id

        result = await db.users.update_one(
            {
                "_id": user_id_obj,
                f"wallet.{currency}": {"$gte": payment_attempt.totalAmount},
            },
            {"$inc": {f"wallet.{currency}": -payment_attempt.totalAmount}},
        )

        if result.modified_count == 0:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = (
                "Saldo insuficiente o modificación concurrente"
            )
            return payment_attempt

        # Credit branch wallet
        branch_id = order.get("branchId")
        await db.branches.update_one(
            {"_id": self._to_object_id(branch_id)},
            {"$inc": {f"wallet.{currency}": amount_to_business}},
        )

        # Credit platform wallet (commission)
        if commission > 0:
            await db.platform.update_one(
                {"_id": "platform"},
                {
                    "$inc": {
                        f"wallet.{currency}": commission,
                        "totalCommissionsCollected": commission
                        if currency == "usd"
                        else 0,
                    }
                },
            )

        # Create transaction records
        now = datetime.utcnow()

        # User debit transaction
        user_tx_id = ObjectId()
        user_tx = {
            "_id": user_tx_id,
            "fromOwnerId": self._to_object_id(user_id),
            "fromOwnerType": "user",
            "toOwnerId": self._to_object_id(order.get("branchId")),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "order_payment",
            "status": "completed",
            "description": f"Pago pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": payment_attempt.id,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(user_tx)

        # Business credit transaction
        business_tx_id = ObjectId()
        business_tx = {
            "_id": business_tx_id,
            "fromOwnerId": self._to_object_id(user_id),
            "fromOwnerType": "user",
            "toOwnerId": self._to_object_id(order.get("branchId")),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "order_received",
            "status": "completed",
            "description": f"Recibido pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": payment_attempt.id,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        # Commission transaction
        commission_tx_id = ObjectId()
        if commission > 0:
            commission_tx = {
                "_id": commission_tx_id,
                "fromOwnerId": self._to_object_id(user_id),
                "fromOwnerType": "user",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission",
                "status": "completed",
                "description": f"Comisión pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": payment_attempt.id,
                },
                "createdAt": now,
                "completedAt": now,
            }
            await db.wallet_transactions.insert_one(commission_tx)

        # Update platform stats
        await db.platform.update_one(
            {"_id": "platform"}, {"$inc": {"totalOrdersProcessed": 1}}
        )

        # Update payment attempt
        payment_attempt.status = PaymentAttemptStatus.COMPLETED
        payment_attempt.completedAt = now
        payment_attempt.walletTransactionId = str(user_tx_id)
        payment_attempt.businessWalletTransactionId = str(business_tx_id)
        payment_attempt.commissionTransactionId = (
            str(commission_tx_id) if commission > 0 else None
        )

        # Update order payment status
        await self._complete_order_payment(str(order.get("_id")), payment_attempt.id)

        return payment_attempt

    async def _create_stripe_payment_intent(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str,
    ) -> PaymentAttempt:
        """Create a Stripe Payment Intent."""
        try:
            # Convert to cents
            amount_cents = int(payment_attempt.totalAmount * 100)

            # Create Payment Intent
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=payment_attempt.currency,
                description=f"Pedido #{order.get('orderNumber', '')} - Llego",
                metadata={
                    "user_id": user_id,
                    "order_id": str(order.get("_id")),
                    "payment_attempt_id": payment_attempt.id,
                    "type": "order_payment",
                },
                automatic_payment_methods={"enabled": True},
            )

            payment_attempt.stripePaymentIntentId = intent.id
            payment_attempt.stripeClientSecret = intent.client_secret
            payment_attempt.status = PaymentAttemptStatus.PROCESSING

            logger.info(
                f"Created Stripe Payment Intent: {intent.id} for order {order.get('_id')}"
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {e}")
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failedReason = f"Error de Stripe: {str(e)}"

        return payment_attempt

    async def confirm_payment_sent(
        self, payment_attempt_id: str, user_id: str, proof_url: str
    ) -> PaymentAttempt:
        """
        Customer confirms they sent the payment (for manual methods).

        Args:
            payment_attempt_id: The payment attempt ID
            user_id: The user confirming
            proof_url: URL to proof/receipt image
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        # Verify ownership
        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.AWAITING_PROOF:
            raise ValueError(f"Estado no válido para confirmar: {attempt.status}")

        # Update attempt
        updated = await self.payment_attempts_repo.set_proof(
            payment_attempt_id, proof_url
        )

        # TODO: Notify business

        return updated

    async def confirm_payment_received(
        self, payment_attempt_id: str, user_id: str
    ) -> PaymentAttempt:
        """
        Business confirms they received the payment.

        Args:
            payment_attempt_id: The payment attempt ID
            user_id: The business user confirming
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify business ownership
        branch = await self._get_branch(order.get("branchId"))
        if not branch:
            raise ValueError("Sucursal no encontrada")

        # Check if user is manager or owner
        business = await businesses_repo.get_by_id(branch.get("businessId"))

        is_authorized = (
            business and business.ownerId == user_id
        ) or user_id in branch.get("managerIds", [])

        if not is_authorized:
            raise ValueError("No autorizado para confirmar este pago")

        if attempt.status != PaymentAttemptStatus.AWAITING_BUSINESS:
            raise ValueError(f"Estado no válido para confirmar: {attempt.status}")

        # Confirm payment
        updated = await self.payment_attempts_repo.confirm_business_received(
            payment_attempt_id
        )

        # Complete order payment
        await self._complete_order_payment(attempt.orderId, payment_attempt_id)

        # TODO: Notify customer

        return updated

    async def confirm_cash_received(
        self, payment_attempt_id: str, delivery_person_id: str
    ) -> PaymentAttempt:
        """
        Delivery person confirms they received cash payment.

        Args:
            payment_attempt_id: The payment attempt ID
            delivery_person_id: The delivery person confirming
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        if attempt.status != PaymentAttemptStatus.AWAITING_DELIVERY:
            raise ValueError(
                f"Estado no válido para confirmar efectivo: {attempt.status}"
            )

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify delivery person is assigned to this order
        if order.get("deliveryPersonId") != delivery_person_id:
            raise ValueError("No autorizado para confirmar este pago")

        # Confirm cash received
        updated = await self.payment_attempts_repo.confirm_delivery_cash(
            payment_attempt_id, delivery_person_id
        )

        # For cash payments, we need to credit the business wallet
        # The cash is physically with the delivery person, but we record it
        await self._process_cash_payment_completion(attempt, order)

        # Complete order payment
        await self._complete_order_payment(attempt.orderId, payment_attempt_id)

        return updated

    async def _process_cash_payment_completion(
        self, attempt: PaymentAttempt, order: dict
    ):
        """Process the wallet transactions for a completed cash payment."""
        db = get_database()
        now = datetime.utcnow()

        # For cash payments, we record the transaction but money flows physically
        # Create transaction records for tracking

        amount_to_business = attempt.subtotal + attempt.deliveryFee
        commission = attempt.commissionAmount
        currency = attempt.currency

        # Record business received (they'll get cash from delivery person)
        business_tx = {
            "_id": ObjectId(),
            "fromOwnerId": self._to_object_id(order.get("customerId")),
            "fromOwnerType": "user",
            "toOwnerId": self._to_object_id(order.get("branchId")),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "cash_payment",
            "status": "completed",
            "description": f"Pago efectivo pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "paymentMethod": "cash",
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        # Commission is owed to platform (to be settled later)
        if commission > 0:
            commission_tx = {
                "_id": ObjectId(),
                "fromOwnerId": self._to_object_id(order.get("branchId")),
                "fromOwnerType": "branch",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission_owed",
                "status": "pending",  # Will be settled when business pays platform
                "description": f"Comisión pendiente pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": attempt.id,
                },
                "createdAt": now,
                "completedAt": None,
            }
            await db.wallet_transactions.insert_one(commission_tx)

    async def dispute_payment(
        self, payment_attempt_id: str, user_id: str, reason: str
    ) -> PaymentAttempt:
        """
        Business disputes that they didn't receive the payment.
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Verify business ownership
        branch = await self._get_branch(order.get("branchId"))
        business = await businesses_repo.get_by_id(branch.get("businessId"))

        is_authorized = (
            business and business.ownerId == user_id
        ) or user_id in branch.get("managerIds", [])

        if not is_authorized:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.AWAITING_BUSINESS:
            raise ValueError(f"Estado no válido para disputar: {attempt.status}")

        return await self.payment_attempts_repo.dispute(payment_attempt_id, reason)

    async def request_refund(
        self, payment_attempt_id: str, user_id: str, reason: str
    ) -> PaymentAttempt:
        """
        Customer requests a refund.
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.COMPLETED:
            raise ValueError("Solo se pueden reembolsar pagos completados")

        # Check if payment method is refundable
        payment_method = await self._get_payment_method(attempt.paymentMethodId)
        if not payment_method or not payment_method.get("isRefundable", True):
            raise ValueError("Este método de pago no permite reembolsos")

        # Check order status - can't refund if already delivered
        non_refundable_statuses = ["delivered", "on_the_way"]
        if order.get("status") in non_refundable_statuses:
            raise ValueError(
                "No se puede reembolsar un pedido ya entregado o en camino"
            )

        return await self.payment_attempts_repo.request_refund(
            payment_attempt_id, reason
        )

    async def process_refund(
        self, payment_attempt_id: str, admin_user_id: str
    ) -> PaymentAttempt:
        """
        Process an approved refund (admin action).
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        if attempt.status != PaymentAttemptStatus.REFUND_REQUESTED:
            raise ValueError("El pago no tiene solicitud de reembolso pendiente")

        # Get payment method to determine refund process
        payment_method = await self._get_payment_method(attempt.paymentMethodId)
        method_type = payment_method.get("method", "").lower() if payment_method else ""

        if method_type == "wallet":
            return await self._process_wallet_refund(attempt)
        elif method_type == "stripe":
            return await self._process_stripe_refund(attempt)
        else:
            # Manual refunds for other methods
            return await self.payment_attempts_repo.update_status(
                payment_attempt_id,
                PaymentAttemptStatus.REFUND_PROCESSING,
            )

    async def _process_wallet_refund(self, attempt: PaymentAttempt) -> PaymentAttempt:
        """Process a wallet refund."""
        db = get_database()
        order = await self._get_order(attempt.orderId)
        now = datetime.utcnow()

        currency = attempt.currency
        refund_amount = (
            attempt.subtotal + attempt.deliveryFee
        )  # Refund without commission

        # Debit from business wallet
        try:
            branch_id = ObjectId(order.get("branchId"))
        except Exception:
            branch_id = order.get("branchId")

        result = await db.branches.update_one(
            {"_id": branch_id, f"wallet.{currency}": {"$gte": refund_amount}},
            {"$inc": {f"wallet.{currency}": -refund_amount}},
        )

        if result.modified_count == 0:
            raise ValueError("El negocio no tiene saldo suficiente para el reembolso")

        # Credit user wallet
        try:
            user_id = ObjectId(order.get("customerId"))
        except Exception:
            user_id = order.get("customerId")

        await db.users.update_one(
            {"_id": user_id}, {"$inc": {f"wallet.{currency}": refund_amount}}
        )

        # Create refund transaction
        refund_tx_id = ObjectId()
        refund_tx = {
            "_id": refund_tx_id,
            "fromOwnerId": self._to_object_id(order.get("branchId")),
            "fromOwnerType": "branch",
            "toOwnerId": self._to_object_id(order.get("customerId")),
            "toOwnerType": "user",
            "amount": refund_amount,
            "currency": currency,
            "type": "refund",
            "status": "completed",
            "description": f"Reembolso pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "originalAmount": attempt.totalAmount,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(refund_tx)

        # Update payment attempt
        return await self.payment_attempts_repo.complete_refund(
            attempt.id, refund_amount, str(refund_tx_id)
        )

    async def _process_stripe_refund(self, attempt: PaymentAttempt) -> PaymentAttempt:
        """Process a Stripe refund."""
        if not attempt.stripePaymentIntentId:
            raise ValueError("No hay Payment Intent de Stripe asociado")

        try:
            # Create Stripe refund
            refund = stripe.Refund.create(
                payment_intent=attempt.stripePaymentIntentId,
                # Refund full amount minus commission (or full amount if you want)
                # For now, refund full amount
            )

            logger.info(f"Stripe refund created: {refund.id}")

            return await self.payment_attempts_repo.complete_refund(
                attempt.id, attempt.totalAmount, refund.id
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            raise ValueError(f"Error de Stripe: {str(e)}")

    async def handle_stripe_webhook(
        self, payment_intent_id: str, event_type: str
    ) -> Optional[PaymentAttempt]:
        """
        Handle Stripe webhook for order payments.

        Args:
            payment_intent_id: Stripe Payment Intent ID
            event_type: Stripe event type
        """
        attempt = await self.payment_attempts_repo.get_by_stripe_payment_intent(
            payment_intent_id
        )

        if not attempt:
            logger.warning(f"No payment attempt found for PI: {payment_intent_id}")
            return None

        if event_type == "payment_intent.succeeded":
            # Payment successful
            updated = await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.COMPLETED,
            )

            # Process the payment completion (credit business, etc.)
            order = await self._get_order(attempt.orderId)
            if order:
                await self._process_stripe_payment_completion(attempt, order)
                await self._complete_order_payment(attempt.orderId, attempt.id)

            return updated

        elif event_type == "payment_intent.payment_failed":
            # Payment failed
            return await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.FAILED,
                failedReason="Pago rechazado por Stripe",
            )

        return attempt

    async def _process_stripe_payment_completion(
        self, attempt: PaymentAttempt, order: dict
    ):
        """Process wallet credits after successful Stripe payment."""
        db = get_database()
        now = datetime.utcnow()

        amount_to_business = attempt.subtotal + attempt.deliveryFee
        commission = attempt.commissionAmount
        currency = attempt.currency

        # Credit business wallet
        branch_id = order.get("branchId")
        await db.branches.update_one(
            {"_id": self._to_object_id(branch_id)},
            {"$inc": {f"wallet.{currency}": amount_to_business}},
        )

        # Credit platform commission
        if commission > 0:
            await db.platform.update_one(
                {"_id": "platform"},
                {
                    "$inc": {
                        f"wallet.{currency}": commission,
                        "totalCommissionsCollected": commission
                        if currency == "usd"
                        else 0,
                    }
                },
            )

        # Create transaction records
        business_tx = {
            "_id": ObjectId(),
            "fromOwnerId": "stripe",
            "fromOwnerType": "external",
            "toOwnerId": self._to_object_id(order.get("branchId")),
            "toOwnerType": "branch",
            "amount": amount_to_business,
            "currency": currency,
            "type": "stripe_payment",
            "status": "completed",
            "description": f"Pago Stripe pedido #{order.get('orderNumber', '')}",
            "metadata": {
                "orderId": str(order.get("_id")),
                "paymentAttemptId": attempt.id,
                "stripePaymentIntentId": attempt.stripePaymentIntentId,
            },
            "createdAt": now,
            "completedAt": now,
        }
        await db.wallet_transactions.insert_one(business_tx)

        if commission > 0:
            commission_tx = {
                "_id": ObjectId(),
                "fromOwnerId": "stripe",
                "fromOwnerType": "external",
                "toOwnerId": "platform",
                "toOwnerType": "platform",
                "amount": commission,
                "currency": currency,
                "type": "commission",
                "status": "completed",
                "description": f"Comisión Stripe pedido #{order.get('orderNumber', '')}",
                "metadata": {
                    "orderId": str(order.get("_id")),
                    "paymentAttemptId": attempt.id,
                },
                "createdAt": now,
                "completedAt": now,
            }
            await db.wallet_transactions.insert_one(commission_tx)

        # Update platform stats
        await db.platform.update_one(
            {"_id": "platform"}, {"$inc": {"totalOrdersProcessed": 1}}
        )

    async def _update_order_payment_attempt(self, order_id: str, attempt_id: str):
        """Update order with current payment attempt ID."""
        db = get_database()
        try:
            order_id_obj = ObjectId(order_id)
        except Exception:
            order_id_obj = order_id

        await db.orders.update_one(
            {"_id": order_id_obj},
            {
                "$set": {
                    "currentPaymentAttemptId": attempt_id,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

    async def _complete_order_payment(self, order_id: str, attempt_id: str):
        """Mark order payment as completed."""
        db = get_database()
        try:
            order_id_obj = ObjectId(order_id)
        except Exception:
            order_id_obj = order_id

        order_doc = await db.orders.find_one({"_id": order_id_obj}, {"status": 1})
        current_status = (order_doc or {}).get("status")
        if current_status == "pending_payment":
            next_status = "accepted"
        elif current_status in {"accepted", "modified_by_store"}:
            next_status = "accepted"
        else:
            # Backward-compatible fallback for older flows
            next_status = "pending_acceptance"

        await db.orders.update_one(
            {"_id": order_id_obj},
            {
                "$set": {
                    "paymentStatus": "completed",
                    "paymentId": attempt_id,
                    "paidAt": datetime.utcnow(),
                    "status": next_status,
                    "updatedAt": datetime.utcnow(),
                }
            },
        )

    async def confirm_transfer_by_shortcut(
        self,
        payment_attempt_id: str,
        user_id: str,
        transfer_id: Optional[str] = None,
    ) -> PaymentAttempt:
        """
        Auto-confirm a transfer payment using a registered Shortcut Transfer.

        Flow:
          1. If transfer_id is None → look up by the user's profile phone number.
          2. If transfer_id is provided → look up by that transfer_id.
          3. If a matching pending shortcut transfer is found → activate it and
             complete the payment immediately (no manual business confirmation needed).

        Args:
            payment_attempt_id: The payment attempt to confirm.
            user_id: The authenticated customer's ID.
            transfer_id: Optional bank transfer reference ID entered by the user.
                         If omitted the user's profile phone is used to match.
        """
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        if attempt.status != PaymentAttemptStatus.AWAITING_PROOF:
            raise ValueError(
                f"El pago no está en espera de comprobante: {attempt.status}"
            )

        # Only allowed for transfer payments where the user indicated SMS will be sent
        if not attempt.sendsSmsNotification:
            raise ValueError("Este pago no fue marcado como transferencia con SMS")

        if transfer_id:
            transfers = await shortcut_transfer_service.find_pending_transfer(
                transfer_id=transfer_id.strip()
            )
        else:
            user = await self._get_user(user_id)
            if not user or not user.get("phone"):
                raise ValueError("El usuario no tiene número de teléfono en su perfil")
            transfers = await shortcut_transfer_service.find_pending_transfer(
                phone=user["phone"]
            )

        if not transfers:
            if transfer_id:
                raise ValueError(
                    "No se encontró una transferencia pendiente con ese ID"
                )
            raise ValueError("phone_not_found")

        matched = transfers[0]

        await shortcut_transfer_service.activate_transfer(matched.id)

        updated = await self.payment_attempts_repo.update_status(
            payment_attempt_id,
            PaymentAttemptStatus.COMPLETED,
            businessConfirmedAt=datetime.utcnow(),
            shortcutTransferId=matched.id,
        )

        await self._complete_order_payment(attempt.orderId, payment_attempt_id)

        return updated

    async def cancel_payment(
        self, payment_attempt_id: str, user_id: str
    ) -> PaymentAttempt:
        """Cancel a pending payment attempt."""
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order or order.get("customerId") != user_id:
            raise ValueError("No autorizado")

        # Can only cancel pending/awaiting payments
        cancellable_statuses = [
            PaymentAttemptStatus.PENDING,
            PaymentAttemptStatus.AWAITING_PROOF,
            PaymentAttemptStatus.PROCESSING,
            PaymentAttemptStatus.AWAITING_KYC,
        ]
        if attempt.status not in cancellable_statuses:
            raise ValueError(
                f"No se puede cancelar un pago en estado: {attempt.status}"
            )

        # If Stripe, cancel the Payment Intent
        if attempt.stripePaymentIntentId:
            try:
                stripe.PaymentIntent.cancel(attempt.stripePaymentIntentId)
            except stripe.error.StripeError as e:
                logger.warning(f"Could not cancel Stripe PI: {e}")

        return await self.payment_attempts_repo.update_status(
            payment_attempt_id,
            PaymentAttemptStatus.CANCELLED,
        )

    async def get_payment_attempt(
        self, payment_attempt_id: str, user_id: str
    ) -> PaymentAttempt:
        """Get a payment attempt with authorization check."""
        attempt = await self.payment_attempts_repo.get_by_id(payment_attempt_id)
        if not attempt:
            raise ValueError("Intento de pago no encontrado")

        order = await self._get_order(attempt.orderId)
        if not order:
            raise ValueError("Pedido no encontrado")

        # Check authorization - customer, business manager, or delivery person
        is_customer = order.get("customerId") == user_id
        is_delivery = order.get("deliveryPersonId") == user_id

        branch = await self._get_branch(order.get("branchId"))
        is_business = user_id in branch.get("managerIds", []) if branch else False

        if not (is_customer or is_business or is_delivery):
            raise ValueError("No autorizado")

        return attempt

    async def expire_payments(self) -> int:
        """
        Expire all payment attempts that have passed their expiration time.
        This should be called by a background job.

        Returns:
            Number of expired payments
        """
        expired = await self.payment_attempts_repo.get_expired()
        count = 0

        for attempt in expired:
            await self.payment_attempts_repo.update_status(
                attempt.id,
                PaymentAttemptStatus.EXPIRED,
            )
            count += 1

            # Optionally notify user
            logger.info(f"Expired payment attempt: {attempt.id}")

        return count


payment_service = PaymentService()
