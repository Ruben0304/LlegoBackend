"""Integration-style tests for cash KYC flow in PaymentService."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai import errors as genai_errors

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from core.config import settings
from domain.payments import PaymentAttemptStatus
from services.kyc.gemini_kyc_adapter import GeminiKycAdapter
from services.payments_service import payment_service

ORDER_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"

GEMINI_KYC_RESPONSE_APPROVED = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            '{"verdict":"valid","confidence_score":0.91,'
                            '"reason_codes":["DOC_VALID","FACE_MATCH_HIGH"],'
                            '"extracted_signals":{"face_match_score":0.93,"spoof_risk_score":0.03},'
                            '"model_version":"kyc-model-test-v1"}'
                        )
                    }
                ]
            }
        }
    ]
}


def _mock_order(payment_method: str = "cash"):
    return {
        "_id": ORDER_ID,
        "customerId": "user1",
        "status": "accepted",
        "branchId": BRANCH_ID,
        "paymentMethod": payment_method,
        "subtotal": 10.0,
        "deliveryFee": 2.0,
    }


def _mock_attempt(status: str = "awaiting_kyc"):
    return SimpleNamespace(
        id="attempt1",
        orderId=ORDER_ID,
        status=status,
        totalAmount=12.0,
        currency="usd",
        latestKycVerificationId=None,
        cashCoverageStatus="blocked",
        kycEvalStatus="pending_evidence",
    )


def _set_kyc_deps(
    monkeypatch,
    *,
    decision_service=None,
    verifications_repo=None,
    audit_repo=None,
    notification_service=None,
):
    decision_service = decision_service or SimpleNamespace(
        get_global_approved=AsyncMock(return_value=None),
        get_reusable_approved=AsyncMock(return_value=None),
        evaluate_cash_kyc=AsyncMock(),
        evaluate_cash_kyc_by_account=AsyncMock(),
        evaluate_global_cash_kyc_with_images=AsyncMock(),
    )
    verifications_repo = verifications_repo or SimpleNamespace(
        get_by_id=AsyncMock(return_value=None),
        get_global_approved=AsyncMock(return_value=None),
        get_latest_global_by_customer=AsyncMock(return_value=None),
        increment_retry=AsyncMock(),
        update_result=AsyncMock(),
    )
    audit_repo = audit_repo or SimpleNamespace(append=AsyncMock())
    notification_service = notification_service or SimpleNamespace(
        notify_merchant=AsyncMock()
    )
    monkeypatch.setattr(
        payment_service,
        "_get_kyc_dependencies",
        lambda: (
            decision_service,
            verifications_repo,
            audit_repo,
            notification_service,
        ),
    )


@pytest.fixture
def patch_payment_repo_ops(monkeypatch):
    monkeypatch.setattr(payment_service.payment_attempts_repo, "create", AsyncMock())
    monkeypatch.setattr(
        payment_service.payment_attempts_repo,
        "get_active_by_order_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(payment_service, "_update_order_payment_attempt", AsyncMock())
    monkeypatch.setattr(
        payment_service,
        "_load_s3_bytes_from_ref",
        lambda _ref: b"fake-image-bytes",
    )


def test_cash_with_kyc_off_allows_cash_uncovered(monkeypatch, patch_payment_repo_ops):
    settings.cash_kyc_feature_enabled = False
    _set_kyc_deps(monkeypatch)
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("cash"))
    )
    monkeypatch.setattr(
        payment_service,
        "_get_payment_method",
        AsyncMock(
            return_value={
                "isActive": True,
                "method": "cash",
                "currency": "USD",
                "commissionPercent": 0,
            }
        ),
    )

    attempt = asyncio.run(
        payment_service.initiate_payment(
            order_id=ORDER_ID,
            payment_method_id="pm-cash",
            user_id="user1",
        )
    )
    assert attempt.status == PaymentAttemptStatus.AWAITING_DELIVERY
    assert attempt.kycRequired is False
    assert attempt.kycEvalStatus == "not_required"
    assert attempt.cashCoverageStatus == "eligible_uncovered"


def test_cash_with_kyc_on_and_reusable_approved(monkeypatch, patch_payment_repo_ops):
    settings.cash_kyc_feature_enabled = True
    _set_kyc_deps(
        monkeypatch,
        decision_service=SimpleNamespace(
            get_global_approved=AsyncMock(
                return_value=SimpleNamespace(id="kyc-reuse-1")
            ),
            get_reusable_approved=AsyncMock(
                return_value=SimpleNamespace(id="kyc-reuse-1")
            ),
            evaluate_cash_kyc=AsyncMock(),
            evaluate_global_cash_kyc_with_images=AsyncMock(),
        ),
    )
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("cash"))
    )
    monkeypatch.setattr(
        payment_service,
        "_get_payment_method",
        AsyncMock(
            return_value={
                "isActive": True,
                "method": "cash",
                "currency": "USD",
                "commissionPercent": 0,
            }
        ),
    )
    monkeypatch.setattr(
        payment_service,
        "_get_branch",
        AsyncMock(
            return_value={
                "id": BRANCH_ID,
                "businessId": "merchant1",
                "cashKycEnabled": True,
                "cashKycPolicyVersion": "cash-kyc-v1",
            }
        ),
    )

    attempt = asyncio.run(
        payment_service.initiate_payment(
            order_id=ORDER_ID,
            payment_method_id="pm-cash",
            user_id="user1",
        )
    )
    assert attempt.status == PaymentAttemptStatus.AWAITING_DELIVERY
    assert attempt.kycRequired is True
    assert attempt.kycEvalStatus == "approved"
    assert attempt.cashCoverageStatus == "eligible_covered"


def test_cash_with_kyc_on_rejected(monkeypatch):
    settings.cash_kyc_feature_enabled = True
    _set_kyc_deps(
        monkeypatch,
        decision_service=SimpleNamespace(
            get_global_approved=AsyncMock(return_value=None),
            get_reusable_approved=AsyncMock(return_value=None),
            evaluate_cash_kyc=AsyncMock(),
            evaluate_global_cash_kyc_with_images=AsyncMock(
                return_value={
                    "verification_id": "kyc1",
                    "kyc_eval_status": "rejected",
                    "cash_coverage_status": "blocked",
                    "next_action": "deny_cash_offer_other_method",
                    "correlation_id": "corr1",
                    "reason_codes": ["DOC_INVALID"],
                }
            ),
        ),
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_attempt()),
    )
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("cash"))
    )
    monkeypatch.setattr(
        payment_service,
        "_get_branch",
        AsyncMock(
            return_value={
                "id": BRANCH_ID,
                "businessId": "merchant1",
                "cashKycEnabled": True,
            }
        ),
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo, "update_status", AsyncMock()
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo, "update_kyc_state", AsyncMock()
    )
    monkeypatch.setattr(
        payment_service, "_load_s3_bytes_from_ref", lambda _ref: b"fake-image-bytes"
    )

    payload = asyncio.run(
        payment_service.start_cash_kyc_evaluation(
            payment_attempt_id="attempt1",
            user_id="user1",
            identity_document_front_ref="s3://doc.jpg",
            selfie_live_ref="s3://selfie.jpg",
            device_context={
                "device_id_hash": "d1",
                "ip_hash": "i1",
                "app_version": "1",
                "os": "iOS",
            },
        )
    )
    assert payload["allowCash"] is False
    assert payload["appCoversCash"] is False
    assert payload["kycEvalStatus"] == "rejected"


def test_cash_with_kyc_on_provider_error_fail_closed(monkeypatch):
    settings.cash_kyc_feature_enabled = True
    _set_kyc_deps(
        monkeypatch,
        decision_service=SimpleNamespace(
            get_global_approved=AsyncMock(return_value=None),
            get_reusable_approved=AsyncMock(return_value=None),
            evaluate_cash_kyc=AsyncMock(),
            evaluate_global_cash_kyc_with_images=AsyncMock(
                return_value={
                    "verification_id": "kyc2",
                    "kyc_eval_status": "error",
                    "cash_coverage_status": "blocked",
                    "next_action": "auto_retry_then_user_retry",
                    "correlation_id": "corr2",
                    "reason_codes": ["PROVIDER_ERROR"],
                    "provider_error": "timeout",
                }
            ),
        ),
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_attempt()),
    )
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("cash"))
    )
    monkeypatch.setattr(
        payment_service,
        "_get_branch",
        AsyncMock(
            return_value={
                "id": BRANCH_ID,
                "businessId": "merchant1",
                "cashKycEnabled": True,
            }
        ),
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo, "update_status", AsyncMock()
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo, "update_kyc_state", AsyncMock()
    )
    monkeypatch.setattr(
        payment_service, "_load_s3_bytes_from_ref", lambda _ref: b"fake-image-bytes"
    )

    payload = asyncio.run(
        payment_service.start_cash_kyc_evaluation(
            payment_attempt_id="attempt1",
            user_id="user1",
            identity_document_front_ref="s3://doc.jpg",
            selfie_live_ref="s3://selfie.jpg",
            device_context={
                "device_id_hash": "d1",
                "ip_hash": "i1",
                "app_version": "1",
                "os": "iOS",
            },
        )
    )
    assert payload["kycEvalStatus"] == "error"
    assert payload["allowCash"] is False


def test_retry_manual_uses_stored_evidence(monkeypatch):
    verification = SimpleNamespace(
        id="kyc3",
        paymentAttemptId="attempt1",
        retryCount=1,
        evidenceRefs=[
            {"type": "identity_document_front", "ref": "s3://doc.jpg"},
            {"type": "selfie_live", "ref": "s3://selfie.jpg"},
        ],
    )
    _set_kyc_deps(
        monkeypatch,
        verifications_repo=SimpleNamespace(
            get_by_id=AsyncMock(return_value=verification),
            increment_retry=AsyncMock(),
            update_result=AsyncMock(),
        ),
    )
    monkeypatch.setattr(
        payment_service.payment_attempts_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_attempt()),
    )
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("cash"))
    )
    monkeypatch.setattr(
        payment_service,
        "start_cash_kyc_evaluation",
        AsyncMock(
            return_value={
                "verificationId": "kyc3",
                "kycEvalStatus": "approved",
                "cashCoverageStatus": "eligible_covered",
                "allowCash": True,
                "appCoversCash": True,
                "nextAction": "continue_cash_flow",
            }
        ),
    )

    result = asyncio.run(payment_service.retry_cash_kyc_evaluation("kyc3", "user1"))
    assert result["verificationId"] == "kyc3"
    payment_service.start_cash_kyc_evaluation.assert_awaited_once()


def test_account_status_reuses_approved_verification(monkeypatch):
    _set_kyc_deps(
        monkeypatch,
        verifications_repo=SimpleNamespace(
            get_global_approved=AsyncMock(
                return_value=SimpleNamespace(
                    id="kyc-account-1",
                    reasonCodes=["DOC_VALID"],
                    expiresAt=None,
                )
            ),
            get_latest_global_by_customer=AsyncMock(return_value=None),
        ),
    )

    status = asyncio.run(
        payment_service.get_cash_kyc_status_by_account(
            merchant_id="merchant1",
            user_id="user1",
        )
    )
    assert status["kycEvalStatus"] == "approved"
    assert status["allowCash"] is True
    assert status["appCoversCash"] is True


def test_start_account_kyc_evaluation_success(monkeypatch):
    _set_kyc_deps(
        monkeypatch,
        decision_service=SimpleNamespace(
            get_global_approved=AsyncMock(return_value=None),
            get_reusable_approved=AsyncMock(return_value=None),
            evaluate_cash_kyc=AsyncMock(),
            evaluate_cash_kyc_by_account=AsyncMock(
                return_value={
                    "verification_id": "kyc-account-2",
                    "kyc_eval_status": "approved",
                    "cash_coverage_status": "eligible_covered",
                    "next_action": "continue_cash_flow",
                    "correlation_id": "corr-account-2",
                    "reason_codes": ["DOC_VALID"],
                }
            ),
            evaluate_global_cash_kyc_with_images=AsyncMock(
                return_value={
                    "verification_id": "kyc-account-2",
                    "kyc_eval_status": "approved",
                    "cash_coverage_status": "eligible_covered",
                    "next_action": "continue_cash_flow",
                    "correlation_id": "corr-account-2",
                    "reason_codes": ["DOC_VALID"],
                }
            ),
        ),
    )
    monkeypatch.setattr(
        payment_service, "_load_s3_bytes_from_ref", lambda _ref: b"fake-image-bytes"
    )

    payload = asyncio.run(
        payment_service.start_cash_kyc_evaluation_by_account(
            merchant_id="merchant1",
            user_id="user1",
            branch_id=BRANCH_ID,
            identity_document_front_ref="s3://doc.jpg",
            selfie_live_ref="s3://selfie.jpg",
            device_context={"device_id_hash": "d1", "ip_hash": "i1"},
        )
    )
    assert payload["verificationId"] == "kyc-account-2"
    assert payload["kycEvalStatus"] == "approved"
    assert payload["appCoversCash"] is True


def test_global_cash_kyc_status_pending_when_no_verification(monkeypatch):
    _set_kyc_deps(
        monkeypatch,
        verifications_repo=SimpleNamespace(
            get_global_approved=AsyncMock(return_value=None),
            get_latest_global_by_customer=AsyncMock(return_value=None),
        ),
    )

    status = asyncio.run(payment_service.get_global_cash_kyc_status(user_id="user1"))
    assert status["kycEvalStatus"] == "pending_evidence"
    assert status["allowCash"] is False


def test_non_cash_flow_regression_transfer_still_awaits_proof(
    monkeypatch, patch_payment_repo_ops
):
    settings.cash_kyc_feature_enabled = True
    _set_kyc_deps(monkeypatch)
    monkeypatch.setattr(
        payment_service, "_get_order", AsyncMock(return_value=_mock_order("transfer"))
    )
    monkeypatch.setattr(
        payment_service,
        "_get_payment_method",
        AsyncMock(
            return_value={
                "isActive": True,
                "method": "transfer",
                "currency": "USD",
                "commissionPercent": 0,
            }
        ),
    )

    attempt = asyncio.run(
        payment_service.initiate_payment(
            order_id=ORDER_ID,
            payment_method_id="pm-transfer",
            user_id="user1",
        )
    )
    assert attempt.status == PaymentAttemptStatus.AWAITING_PROOF


def test_gemini_adapter_auto_retry_transient(monkeypatch):
    settings.gemini_api_key = "test"
    adapter = GeminiKycAdapter()

    class FakeResponse:
        text = (
            '{"verdict":"valid","confidence_score":0.91,'
            '"reason_codes":["DOC_VALID","FACE_MATCH_HIGH"],'
            '"extracted_signals":{"face_match_score":0.93,"spoof_risk_score":0.03},'
            '"model_version":"kyc-model-test-v1"}'
        )

    class FakeAioModels:
        calls = 0

        async def generate_content(self, *args, **kwargs):
            FakeAioModels.calls += 1
            if FakeAioModels.calls == 1:
                raise genai_errors.ServerError(
                    503,
                    {"error": {"message": "backend overloaded"}},
                )
            return FakeResponse()

    class FakeClient:
        aio = SimpleNamespace(models=FakeAioModels())

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("services.kyc.gemini_kyc_adapter.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(adapter, "_get_client", lambda: FakeClient())

    result = asyncio.run(
        adapter.evaluate(
            {
                "request_id": "r1",
                "correlation_id": "c1",
                "policy_version": "cash-kyc-v1",
            }
        )
    )
    assert result["verdict"] == "valid"
    assert result["confidence_score"] == 0.91


def test_gemini_adapter_structured_text_parsing(monkeypatch):
    settings.gemini_api_key = "test"
    adapter = GeminiKycAdapter()

    class FakeResponse:
        text = (
            '{"verdict":"valid","confidence_score":0.88,'
            '"reason_codes":["DOC_VALID"],'
            '"extracted_signals":{"face_match_score":0.91},'
            '"model_version":"gemini-kyc-test"}'
        )

    class FakeAioModels:
        async def generate_content(self, *args, **kwargs):
            return FakeResponse()

    class FakeClient:
        aio = SimpleNamespace(models=FakeAioModels())

    monkeypatch.setattr(adapter, "_get_client", lambda: FakeClient())

    result = asyncio.run(
        adapter.evaluate(
            {
                "request_id": "r2",
                "correlation_id": "c2",
                "policy_version": "cash-kyc-v1",
            }
        )
    )
    assert result["verdict"] == "valid"
    assert result["confidence_score"] == 0.88
    assert result["reason_codes"] == ["DOC_VALID"]
    assert "error" not in result


def test_gemini_adapter_returns_exact_provider_error(monkeypatch):
    settings.gemini_api_key = "test"
    adapter = GeminiKycAdapter()

    class FakeAioModels:
        async def generate_content(self, *args, **kwargs):
            raise genai_errors.ClientError(
                400,
                {
                    "error": {
                        "message": "The input image is too large.",
                    }
                },
            )

    class FakeClient:
        aio = SimpleNamespace(models=FakeAioModels())

    monkeypatch.setattr(adapter, "_get_client", lambda: FakeClient())

    result = asyncio.run(
        adapter.evaluate_with_images(
            request_payload={
                "request_id": "r3",
                "correlation_id": "c3",
                "policy_version": "cash-kyc-v1",
            },
            selfie_with_id_bytes=b"img-1",
            selfie_with_id_mime_type="image/jpeg",
            identity_document_front_bytes=b"img-2",
            identity_document_front_mime_type="image/jpeg",
        )
    )
    assert result["verdict"] == "error"
    assert result["reason_codes"] == ["PROVIDER_ERROR"]
    assert "too large" in result["error"]
    assert result["error_code"] == "GEMINI_PROVIDER_ERROR"


def test_gemini_adapter_maps_high_demand_error_code(monkeypatch):
    settings.gemini_api_key = "test"
    adapter = GeminiKycAdapter()

    class FakeAioModels:
        async def generate_content(self, *args, **kwargs):
            raise genai_errors.ServerError(
                503,
                {
                    "error": {
                        "message": (
                            "This model is currently experiencing high demand. "
                            "Spikes in demand are usually temporary. Please try again later."
                        ),
                    }
                },
            )

    class FakeClient:
        aio = SimpleNamespace(models=FakeAioModels())

    monkeypatch.setattr(adapter, "_get_client", lambda: FakeClient())

    result = asyncio.run(
        adapter.evaluate_with_images(
            request_payload={
                "request_id": "r4",
                "correlation_id": "c4",
                "policy_version": "cash-kyc-v1",
            },
            selfie_with_id_bytes=b"img-1",
            selfie_with_id_mime_type="image/jpeg",
            identity_document_front_bytes=b"img-2",
            identity_document_front_mime_type="image/jpeg",
        )
    )
    assert result["verdict"] == "error"
    assert result["error_code"] == "GEMINI_MODEL_OVERLOADED"
    assert "high demand" in result["error"]
