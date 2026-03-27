"""Integration-style tests for cash KYC flow in PaymentService."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
        get_reusable_approved=AsyncMock(return_value=None),
        evaluate_cash_kyc=AsyncMock(),
    )
    verifications_repo = verifications_repo or SimpleNamespace(
        get_by_id=AsyncMock(return_value=None),
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
            get_reusable_approved=AsyncMock(
                return_value=SimpleNamespace(id="kyc-reuse-1")
            ),
            evaluate_cash_kyc=AsyncMock(),
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
            get_reusable_approved=AsyncMock(return_value=None),
            evaluate_cash_kyc=AsyncMock(
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
            get_reusable_approved=AsyncMock(return_value=None),
            evaluate_cash_kyc=AsyncMock(
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
        def __init__(self, status_code, payload=None):
            import httpx

            self.status_code = status_code
            self._payload = payload or {}
            self.request = httpx.Request("POST", "https://example.com")

        def raise_for_status(self):
            import httpx

            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error", request=self.request, response=self
                )

        def json(self):
            return self._payload

    class FakeClient:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            FakeClient.calls += 1
            if FakeClient.calls == 1:
                return FakeResponse(429, {})
            return FakeResponse(200, GEMINI_KYC_RESPONSE_APPROVED)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("services.kyc.gemini_kyc_adapter.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("services.kyc.gemini_kyc_adapter.asyncio.sleep", _no_sleep)

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
