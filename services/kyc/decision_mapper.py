"""Decision mapping for KYC verdict to backend statuses."""

from typing import Dict, Optional

from domain.kyc import CashCoverageStatus, KycEvalStatus


def map_kyc_decision(verdict: str, confidence_score: Optional[float]) -> Dict[str, str]:
    """Map provider verdict + confidence to internal statuses."""
    verdict_value = (verdict or "error").lower()
    confidence = confidence_score if confidence_score is not None else 0.0

    if verdict_value == "valid":
        if confidence >= 0.85:
            return {
                "kyc_eval_status": KycEvalStatus.APPROVED.value,
                "cash_coverage_status": CashCoverageStatus.ELIGIBLE_COVERED.value,
                "next_action": "continue_cash_flow",
            }
        if confidence >= 0.60:
            return {
                "kyc_eval_status": KycEvalStatus.NEEDS_REVIEW.value,
                "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
                "next_action": "request_new_evidence",
            }
        return {
            "kyc_eval_status": KycEvalStatus.INSUFFICIENT_DATA.value,
            "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
            "next_action": "request_new_evidence",
        }

    if verdict_value == "invalid":
        return {
            "kyc_eval_status": KycEvalStatus.REJECTED.value,
            "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
            "next_action": "deny_cash_offer_other_method",
        }

    if verdict_value == "needs_review":
        return {
            "kyc_eval_status": KycEvalStatus.NEEDS_REVIEW.value,
            "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
            "next_action": "request_new_evidence",
        }

    if verdict_value == "insufficient_data":
        return {
            "kyc_eval_status": KycEvalStatus.INSUFFICIENT_DATA.value,
            "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
            "next_action": "request_new_evidence",
        }

    return {
        "kyc_eval_status": KycEvalStatus.ERROR.value,
        "cash_coverage_status": CashCoverageStatus.BLOCKED.value,
        "next_action": "auto_retry_then_user_retry",
    }
