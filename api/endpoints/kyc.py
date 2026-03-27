"""REST endpoints for global account KYC with real image uploads."""

from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from services.payments_service import payment_service
from utils.auth import get_current_user_id_from_header
from utils.rate_limit import RATE_LIMIT_UPLOADS, limiter
from utils.s3 import upload_file

router = APIRouter(prefix="/kyc", tags=["KYC"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_KYC_IMAGE_SIZE = 12 * 1024 * 1024  # 12MB per image


def _extension_from_mime(content_type: str) -> str:
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    return ".jpg"


async def _validate_image(file: UploadFile) -> bytes:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo de imagen no permitido (JPEG/PNG/WEBP)",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imagen vacía",
        )
    if len(content) > MAX_KYC_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Imagen demasiado grande (máximo 12MB)",
        )

    try:
        from PIL import Image

        img = Image.open(BytesIO(content))
        img.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imagen inválida o corrupta",
        ) from exc

    return content


@router.post("/global/evaluate")
@limiter.limit(RATE_LIMIT_UPLOADS)
async def evaluate_global_kyc(
    request: Request,
    selfie_with_id: UploadFile = File(
        ..., description="Selfie sosteniendo documento de identidad"
    ),
    identity_document_front: UploadFile = File(
        ..., description="Foto frontal del documento de identidad"
    ),
    user_id: str = Depends(get_current_user_id_from_header),
):
    """Upload real KYC images and run global account KYC evaluation."""
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")

    selfie_bytes = await _validate_image(selfie_with_id)
    doc_bytes = await _validate_image(identity_document_front)

    selfie_ref = await upload_file(
        selfie_bytes,
        "kyc/global/selfie_with_id",
        user_id,
        _extension_from_mime(selfie_with_id.content_type or "image/jpeg"),
        generate_thumbnails=False,
    )
    doc_ref = await upload_file(
        doc_bytes,
        "kyc/global/identity_document_front",
        user_id,
        _extension_from_mime(identity_document_front.content_type or "image/jpeg"),
        generate_thumbnails=False,
    )

    try:
        result = await payment_service.start_cash_kyc_evaluation_by_account(
            merchant_id="global",
            user_id=user_id,
            branch_id=None,
            identity_document_front_ref=doc_ref,
            selfie_live_ref=selfie_ref,
            device_context={"source": "rest_upload"},
        )
        return {
            "verificationId": result["verificationId"],
            "kycEvalStatus": result["kycEvalStatus"],
            "cashCoverageStatus": result["cashCoverageStatus"],
            "allowCash": result["allowCash"],
            "appCoversCash": result["appCoversCash"],
            "nextAction": result["nextAction"],
            "correlationId": result["correlationId"],
            "reasonCodes": result["reasonCodes"],
            "evidenceRefs": {
                "selfie_with_id": selfie_ref,
                "identity_document_front": doc_ref,
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
