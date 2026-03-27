"""Reusable mock fixtures for Gemini KYC contract tests."""

GEMINI_KYC_REQUEST = {
    "request_id": "req-123",
    "correlation_id": "corr-123",
    "idempotency_key": "idem-123",
    "policy_version": "cash-kyc-v1",
    "subject": {
        "user_id": "user1",
        "merchant_id": "merchant1",
        "branch_id": "branch1",
    },
    "transaction": {
        "payment_attempt_id": "attempt1",
        "order_id": "order1",
        "amount": 25.5,
        "currency": "USD",
        "timestamp": "2026-03-27T12:00:00Z",
    },
    "evidence": [
        {"type": "identity_document_front", "ref": "s3://bucket/doc-front.jpg"},
        {"type": "selfie_live", "ref": "s3://bucket/selfie.jpg"},
    ],
    "device_context": {
        "device_id_hash": "hash-device",
        "ip_hash": "hash-ip",
        "app_version": "2.0.0",
        "os": "iOS",
    },
}

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

GEMINI_KYC_RESPONSE_REJECTED = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            '{"verdict":"invalid","confidence_score":0.95,'
                            '"reason_codes":["DOC_INVALID"],'
                            '"extracted_signals":{"face_match_score":0.2},'
                            '"model_version":"kyc-model-test-v1"}'
                        )
                    }
                ]
            }
        }
    ]
}
