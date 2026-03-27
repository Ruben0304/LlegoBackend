"""Unit tests for KYC idempotency/evidence hashing helpers."""

import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from services.kyc.kyc_decision_service import KycDecisionService


def test_evidence_hash_is_deterministic():
    service = KycDecisionService()
    evidence_a = [
        {"type": "selfie_live", "ref": "s3://bucket/a.jpg"},
        {"type": "identity_document_front", "ref": "s3://bucket/b.jpg"},
    ]
    evidence_b = [
        {"type": "identity_document_front", "ref": "s3://bucket/b.jpg"},
        {"type": "selfie_live", "ref": "s3://bucket/a.jpg"},
    ]
    assert service.build_evidence_hash(evidence_a) == service.build_evidence_hash(
        evidence_b
    )


def test_idempotency_key_changes_with_policy_version():
    service = KycDecisionService()
    key_v1 = service.build_idempotency_key("attempt1", "hash123", "cash-kyc-v1")
    key_v2 = service.build_idempotency_key("attempt1", "hash123", "cash-kyc-v2")
    assert key_v1 != key_v2
