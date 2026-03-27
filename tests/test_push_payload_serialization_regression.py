"""Regression tests for push payload serialization."""

import os

from bson import ObjectId

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

from services.push_notification_service import _normalize_push_payload


def test_normalize_push_payload_converts_objectid_recursively():
    oid = ObjectId()
    payload = {
        "error_id": oid,
        "nested": {"ids": [oid, {"inner": oid}]},
    }

    normalized = _normalize_push_payload(payload)

    assert normalized["error_id"] == str(oid)
    assert normalized["nested"]["ids"][0] == str(oid)
    assert normalized["nested"]["ids"][1]["inner"] == str(oid)
