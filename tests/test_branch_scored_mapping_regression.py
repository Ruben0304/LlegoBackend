"""Regression tests for scored branch mapping with extra branch fields."""

import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from schema.branches.queries import _to_scored_branch_data


def test_scored_branch_mapper_filters_kyc_fields():
    data = {
        "id": "b1",
        "businessId": "m1",
        "name": "Sucursal",
        "coordinates": {"type": "Point", "coordinates": [-82.3, 23.1]},
        "phone": "555",
        "schedule": {},
        "managerIds": [],
        "isActive": True,
        "tipos": [],
        "paymentMethodIds": [],
        "createdAt": "2026-03-27T00:00:00Z",
        "wallet": {"local": 0, "usd": 0},
        "cashKycEnabled": True,
        "cashKycPolicyVersion": "cash-kyc-v1",
        "cashKycMinConfidence": 0.85,
        "cashKycTtlDays": 30,
        "forceReverify": False,
    }

    mapped = _to_scored_branch_data(data)

    assert "cashKycEnabled" not in mapped
    assert "cashKycPolicyVersion" not in mapped
    assert "cashKycMinConfidence" not in mapped
    assert "cashKycTtlDays" not in mapped
    assert "forceReverify" not in mapped
    assert mapped["id"] == "b1"
