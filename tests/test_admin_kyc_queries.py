"""Unit tests for the admin KYC review queue (queries) and the
override_cash_kyc_decision role guard (mutation).

Same convention as tests/test_branch_delivery_request_concurrency.py:
resolver logic against mocked repositories/services, no live or mocked
MongoDB (see tests/test_cash_kyc_integration.py for why).
"""

import asyncio
import json
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.payments.mutations as mutations
import schema.payments.queries as queries
from schema.payments.types import OverrideCashKycInput, KycOverrideDecisionEnum

VERIFICATION_ID = "507f1f77bcf86cd799439011"
CUSTOMER_ID = "507f1f77bcf86cd799439012"


def _mock_verification(**overrides):
    defaults = dict(
        id=VERIFICATION_ID,
        kycScope="global_account",
        verificationSource="checkout",
        paymentAttemptId=None,
        orderId=None,
        customerId=CUSTOMER_ID,
        merchantId=None,
        branchId=None,
        verdict="needs_review",
        confidenceScore=0.7,
        reasonCodes=["FACE_MATCH_LOW"],
        extractedSignals={"face_match_score": 0.7},
        status="needs_review",
        retryCount=0,
        lastError=None,
        evaluatedAt=datetime(2026, 1, 1),
        approvedAt=None,
        expiresAt=None,
        createdAt=datetime(2026, 1, 1),
        updatedAt=datetime(2026, 1, 1),
        evidenceRefs=[
            {"type": "identity_document_front", "ref": "kyc/doc.jpg"},
            {"type": "selfie_live", "ref": "kyc/selfie.jpg"},
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def stub_signed_urls(monkeypatch):
    """Evidence URL generation touches AWS/S3 — stub it in every test here."""
    monkeypatch.setattr(
        "utils.s3.get_public_url", lambda key, expiration=3600: f"https://signed/{key}"
    )


def test_admin_kyc_verifications_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception(f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}")

    monkeypatch.setattr(queries, "require_role", _deny)
    list_filtered = AsyncMock()
    monkeypatch.setattr(queries.kyc_verifications_repo, "list_filtered", list_filtered)

    query = queries.PaymentMethodQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            query.admin_kyc_verifications(info=None, jwt="token")
        )
    list_filtered.assert_not_awaited()


def test_admin_kyc_verifications_assembles_connection_from_repo(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    rows = [_mock_verification(), _mock_verification(id="507f1f77bcf86cd799439099")]
    monkeypatch.setattr(
        queries.kyc_verifications_repo,
        "list_filtered",
        AsyncMock(return_value=(rows, 2)),
    )

    query = queries.PaymentMethodQuery()
    result = asyncio.run(
        query.admin_kyc_verifications(
            info=None, jwt="token", statusIn=["needs_review"], limit=50, offset=0
        )
    )

    assert result.totalCount == 2
    assert result.hasMore is False
    assert len(result.rows) == 2
    first = result.rows[0]
    assert first.id == VERIFICATION_ID
    assert first.verdict == "needs_review"
    assert first.confidenceScore == 0.7
    assert first.reasonCodes == ["FACE_MATCH_LOW"]
    assert json.loads(first.extractedSignalsJson) == {"face_match_score": 0.7}
    assert len(first.evidence) == 2
    assert first.evidence[0].type == "identity_document_front"
    assert first.evidence[0].url == "https://signed/kyc/doc.jpg"


def test_admin_kyc_verifications_has_more_when_offset_plus_rows_below_total(
    monkeypatch,
):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    rows = [_mock_verification()]
    monkeypatch.setattr(
        queries.kyc_verifications_repo,
        "list_filtered",
        AsyncMock(return_value=(rows, 5)),
    )

    query = queries.PaymentMethodQuery()
    result = asyncio.run(
        query.admin_kyc_verifications(info=None, jwt="token", limit=1, offset=0)
    )

    assert result.hasMore is True


def test_admin_kyc_audit_events_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception("Acceso denegado")

    monkeypatch.setattr(queries, "require_role", _deny)
    list_by_entity = AsyncMock()
    monkeypatch.setattr(queries.kyc_audit_events_repo, "list_by_entity", list_by_entity)

    query = queries.PaymentMethodQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            query.admin_kyc_audit_events(
                info=None, verificationId=VERIFICATION_ID, jwt="token"
            )
        )
    list_by_entity.assert_not_awaited()


def test_admin_kyc_audit_events_maps_repo_results(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    event = SimpleNamespace(
        entityType="kyc_verification",
        entityId=VERIFICATION_ID,
        eventType="kyc_override",
        actorType="admin",
        actorId="admin-id",
        payload={"decision": "approve", "reason": "Manual review OK"},
        createdAt=datetime(2026, 1, 2),
    )
    monkeypatch.setattr(
        queries.kyc_audit_events_repo,
        "list_by_entity",
        AsyncMock(return_value=[event]),
    )

    query = queries.PaymentMethodQuery()
    result = asyncio.run(
        query.admin_kyc_audit_events(
            info=None, verificationId=VERIFICATION_ID, jwt="token"
        )
    )

    assert len(result) == 1
    assert result[0].eventType == "kyc_override"
    assert json.loads(result[0].payloadJson) == {
        "decision": "approve",
        "reason": "Manual review OK",
    }


def test_override_cash_kyc_decision_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception(
            f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}"
        )

    monkeypatch.setattr(mutations, "require_role", _deny)
    override = AsyncMock()
    monkeypatch.setattr(
        mutations.payment_service, "override_cash_kyc_decision", override
    )

    mutation = mutations.PaymentMutation()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            mutation.override_cash_kyc_decision(
                info=None,
                input=OverrideCashKycInput(
                    verificationId=VERIFICATION_ID,
                    decision=KycOverrideDecisionEnum.APPROVE,
                    reason="test",
                ),
                jwt="token",
            )
        )
    override.assert_not_awaited()
