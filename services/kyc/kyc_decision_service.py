"""Cash KYC decision service."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from bson import ObjectId

from core.config import settings
from domain.kyc import KycEvalStatus, KycScope, KycVerification
from repositories.kyc_verification_repository import kyc_verifications_repo

from .decision_mapper import map_kyc_decision
from .gemini_kyc_adapter import gemini_kyc_adapter


class KycDecisionService:
    """Coordinates KYC request lifecycle and provider integration."""

    @staticmethod
    def build_evidence_hash(evidence_refs: List[Dict[str, str]]) -> str:
        payload = json.dumps(
            sorted(evidence_refs, key=lambda x: x.get("type", "")), sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def build_idempotency_key(
        scope_key: str, evidence_hash: str, policy_version: str
    ) -> str:
        raw = f"{scope_key}:{evidence_hash}:{policy_version}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get_reusable_approved(
        self,
        *,
        customer_id: str,
        merchant_id: str,
        policy_version: str,
    ) -> Optional[KycVerification]:
        return await kyc_verifications_repo.get_reusable_approved(
            customer_id=customer_id,
            merchant_id=merchant_id,
            policy_version=policy_version,
        )

    async def get_global_approved(
        self,
        *,
        customer_id: str,
    ) -> Optional[KycVerification]:
        return await kyc_verifications_repo.get_global_approved(customer_id=customer_id)

    async def _evaluate(
        self,
        *,
        verification_source: str,
        payment_attempt_id: Optional[str],
        order_id: Optional[str],
        customer_id: str,
        merchant_id: str,
        branch_id: Optional[str],
        amount: Optional[float],
        currency: Optional[str],
        policy_version: str,
        min_confidence: float,
        ttl_days: int,
        evidence_refs: List[Dict[str, str]],
        device_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        request_id = str(uuid4())
        correlation_id = str(uuid4())
        evidence_hash = self.build_evidence_hash(evidence_refs)
        scope_key = (
            payment_attempt_id
            or f"account:{customer_id}:{merchant_id}:{verification_source}"
        )
        idempotency_key = self.build_idempotency_key(
            scope_key, evidence_hash, policy_version
        )

        verification = KycVerification(
            _id=str(ObjectId()),
            kycScope=KycScope.MERCHANT_SCOPED.value,
            verificationSource=verification_source,
            paymentAttemptId=payment_attempt_id,
            orderId=order_id,
            customerId=customer_id,
            merchantId=merchant_id,
            branchId=branch_id,
            policyVersion=policy_version,
            minConfidence=min_confidence,
            evidenceRefs=evidence_refs,
            evidenceHash=evidence_hash,
            requestId=request_id,
            correlationId=correlation_id,
            idempotencyKey=idempotency_key,
            status=KycEvalStatus.SUBMITTED.value,
        )
        await kyc_verifications_repo.create(verification)

        provider_request = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "policy_version": policy_version,
            "subject": {
                "user_id": customer_id,
                "merchant_id": merchant_id,
                "branch_id": branch_id,
            },
            "transaction": {
                "payment_attempt_id": payment_attempt_id,
                "order_id": order_id,
                "amount": amount if amount is not None else 0.0,
                "currency": currency or "unknown",
                "timestamp": now.isoformat(),
            },
            "evidence": evidence_refs,
            "device_context": device_context,
        }

        provider_result = await gemini_kyc_adapter.evaluate(provider_request)
        mapped = map_kyc_decision(
            provider_result.get("verdict", "error"),
            provider_result.get("confidence_score"),
        )

        kyc_status = mapped["kyc_eval_status"]
        expires_at = None
        if kyc_status == KycEvalStatus.APPROVED.value:
            expires_at = datetime.utcnow() + timedelta(
                days=ttl_days or settings.cash_kyc_default_ttl_days
            )

        updated = await kyc_verifications_repo.update_result(
            verification_id=str(verification.id),
            status=kyc_status,
            verdict=provider_result.get("verdict"),
            confidence_score=provider_result.get("confidence_score"),
            reason_codes=provider_result.get("reason_codes"),
            extracted_signals=provider_result.get("extracted_signals"),
            model_version=provider_result.get("model_version"),
            evaluated_at=datetime.utcnow(),
            expires_at=expires_at,
            last_error=provider_result.get("error"),
        )

        return {
            "verification_id": str(updated.id) if updated else str(verification.id),
            "correlation_id": correlation_id,
            "request_id": request_id,
            "verdict": provider_result.get("verdict", "error"),
            "confidence_score": provider_result.get("confidence_score", 0.0),
            "reason_codes": provider_result.get("reason_codes", []),
            "extracted_signals": provider_result.get("extracted_signals", {}),
            "model_version": provider_result.get("model_version"),
            "kyc_eval_status": mapped["kyc_eval_status"],
            "cash_coverage_status": mapped["cash_coverage_status"],
            "next_action": mapped["next_action"],
            "expires_at": expires_at,
            "provider_error": provider_result.get("error"),
        }

    async def evaluate_global_cash_kyc_with_images(
        self,
        *,
        customer_id: str,
        policy_version: str,
        min_confidence: float,
        ttl_days: int,
        evidence_refs: List[Dict[str, str]],
        device_context: Dict[str, Any],
        selfie_with_id_bytes: bytes,
        selfie_with_id_mime_type: str,
        identity_document_front_bytes: bytes,
        identity_document_front_mime_type: str,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        request_id = str(uuid4())
        correlation_id = str(uuid4())
        evidence_hash = self.build_evidence_hash(evidence_refs)
        scope_key = f"global:{customer_id}"
        idempotency_key = self.build_idempotency_key(
            scope_key, evidence_hash, policy_version
        )

        verification = KycVerification(
            _id=str(ObjectId()),
            kycScope=KycScope.GLOBAL_ACCOUNT.value,
            verificationSource="account_global",
            paymentAttemptId=None,
            orderId=None,
            customerId=customer_id,
            merchantId=None,
            branchId=None,
            policyVersion=policy_version,
            minConfidence=min_confidence,
            evidenceRefs=evidence_refs,
            evidenceHash=evidence_hash,
            requestId=request_id,
            correlationId=correlation_id,
            idempotencyKey=idempotency_key,
            status=KycEvalStatus.SUBMITTED.value,
        )
        await kyc_verifications_repo.create(verification)

        provider_request = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "policy_version": policy_version,
            "subject": {
                "user_id": customer_id,
            },
            "context": {
                "flow": "global_account_kyc",
                "timestamp": now.isoformat(),
            },
            "evidence": evidence_refs,
            "device_context": device_context,
        }

        provider_result = await gemini_kyc_adapter.evaluate_with_images(
            request_payload=provider_request,
            selfie_with_id_bytes=selfie_with_id_bytes,
            selfie_with_id_mime_type=selfie_with_id_mime_type,
            identity_document_front_bytes=identity_document_front_bytes,
            identity_document_front_mime_type=identity_document_front_mime_type,
        )
        mapped = map_kyc_decision(
            provider_result.get("verdict", "error"),
            provider_result.get("confidence_score"),
        )

        kyc_status = mapped["kyc_eval_status"]
        expires_at = None
        if kyc_status == KycEvalStatus.APPROVED.value:
            expires_at = datetime.utcnow() + timedelta(
                days=ttl_days or settings.cash_kyc_default_ttl_days
            )

        updated = await kyc_verifications_repo.update_result(
            verification_id=str(verification.id),
            status=kyc_status,
            verdict=provider_result.get("verdict"),
            confidence_score=provider_result.get("confidence_score"),
            reason_codes=provider_result.get("reason_codes"),
            extracted_signals=provider_result.get("extracted_signals"),
            model_version=provider_result.get("model_version"),
            evaluated_at=datetime.utcnow(),
            expires_at=expires_at,
            last_error=provider_result.get("error"),
        )

        return {
            "verification_id": str(updated.id) if updated else str(verification.id),
            "correlation_id": correlation_id,
            "request_id": request_id,
            "verdict": provider_result.get("verdict", "error"),
            "confidence_score": provider_result.get("confidence_score", 0.0),
            "reason_codes": provider_result.get("reason_codes", []),
            "extracted_signals": provider_result.get("extracted_signals", {}),
            "model_version": provider_result.get("model_version"),
            "kyc_eval_status": mapped["kyc_eval_status"],
            "cash_coverage_status": mapped["cash_coverage_status"],
            "next_action": mapped["next_action"],
            "expires_at": expires_at,
            "provider_error": provider_result.get("error"),
        }

    async def evaluate_cash_kyc(
        self,
        *,
        payment_attempt_id: str,
        order_id: str,
        customer_id: str,
        merchant_id: str,
        branch_id: str,
        amount: float,
        currency: str,
        policy_version: str,
        min_confidence: float,
        ttl_days: int,
        evidence_refs: List[Dict[str, str]],
        device_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await self._evaluate(
            verification_source="checkout",
            payment_attempt_id=payment_attempt_id,
            order_id=order_id,
            customer_id=customer_id,
            merchant_id=merchant_id,
            branch_id=branch_id,
            amount=amount,
            currency=currency,
            policy_version=policy_version,
            min_confidence=min_confidence,
            ttl_days=ttl_days,
            evidence_refs=evidence_refs,
            device_context=device_context,
        )

    async def evaluate_cash_kyc_by_account(
        self,
        *,
        customer_id: str,
        merchant_id: str,
        branch_id: Optional[str],
        policy_version: str,
        min_confidence: float,
        ttl_days: int,
        evidence_refs: List[Dict[str, str]],
        device_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await self._evaluate(
            verification_source="account",
            payment_attempt_id=None,
            order_id=None,
            customer_id=customer_id,
            merchant_id=merchant_id,
            branch_id=branch_id,
            amount=None,
            currency=None,
            policy_version=policy_version,
            min_confidence=min_confidence,
            ttl_days=ttl_days,
            evidence_refs=evidence_refs,
            device_context=device_context,
        )


kyc_decision_service = KycDecisionService()
