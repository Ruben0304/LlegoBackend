"""Unit tests for cash KYC decision mapping."""

from services.kyc.decision_mapper import map_kyc_decision


def test_valid_high_confidence_approved():
    result = map_kyc_decision("valid", 0.91)
    assert result["kyc_eval_status"] == "approved"
    assert result["cash_coverage_status"] == "eligible_covered"
    assert result["next_action"] == "continue_cash_flow"


def test_valid_mid_confidence_needs_review():
    result = map_kyc_decision("valid", 0.7)
    assert result["kyc_eval_status"] == "needs_review"
    assert result["cash_coverage_status"] == "blocked"


def test_valid_low_confidence_insufficient_data():
    result = map_kyc_decision("valid", 0.3)
    assert result["kyc_eval_status"] == "insufficient_data"
    assert result["cash_coverage_status"] == "blocked"


def test_invalid_is_rejected():
    result = map_kyc_decision("invalid", 1.0)
    assert result["kyc_eval_status"] == "rejected"
    assert result["cash_coverage_status"] == "blocked"


def test_error_is_fail_closed():
    result = map_kyc_decision("error", None)
    assert result["kyc_eval_status"] == "error"
    assert result["cash_coverage_status"] == "blocked"
    assert result["next_action"] == "auto_retry_then_user_retry"
