"""POST /kyc/global/evaluate emite el log de finalizacion.

Antes el endpoint hacia `return {...}` antes del log `kyc_evaluation_completed`
y dejaba detras un `return response` inalcanzable con `response` sin definir
(context.md §12.7): la respuesta era correcta pero el log nunca salia.
"""

import logging
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.endpoints import kyc
from utils.auth import get_current_user_id_from_header
from utils.rate_limit import limiter

RESULT = {
    "verificationId": "ver-1",
    "kycEvalStatus": "valid",
    "cashCoverageStatus": "covered",
    "allowCash": True,
    "appCoversCash": False,
    "nextAction": "none",
    "correlationId": "corr-1",
    "reasonCodes": [],
}


def test_evaluate_returns_result_and_logs_completion(caplog):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(kyc.router)
    app.dependency_overrides[get_current_user_id_from_header] = lambda: "user-kyc-log"
    limiter.reset()

    with patch.object(kyc, "_validate_image", AsyncMock(return_value=b"img")), \
         patch.object(kyc, "upload_file", AsyncMock(side_effect=["kyc/selfie.jpg", "kyc/doc.jpg"])), \
         patch.object(
             kyc.payment_service,
             "start_cash_kyc_evaluation_by_account",
             AsyncMock(return_value=RESULT),
         ), caplog.at_level(logging.INFO, logger=kyc.logger.name):
        res = TestClient(app).post(
            "/kyc/global/evaluate",
            files={
                "selfie_with_id": ("s.jpg", b"x", "image/jpeg"),
                "identity_document_front": ("d.jpg", b"x", "image/jpeg"),
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["verificationId"] == "ver-1"
    assert body["evidenceRefs"] == {
        "selfie_with_id": "kyc/selfie.jpg",
        "identity_document_front": "kyc/doc.jpg",
    }
    assert any("kyc_evaluation_completed" in r.getMessage() for r in caplog.records)
