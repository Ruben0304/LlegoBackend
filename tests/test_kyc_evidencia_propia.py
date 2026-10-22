"""KYC del efectivo: la evidencia tiene que ser una foto subida por el propio usuario."""
import pytest

from services.payments_service import PaymentService

UID = "a" * 24


@pytest.mark.parametrize(
    "ref",
    [f"kyc/evidence/{UID}_1700000000.jpg", f"users/avatars/{UID}_1700000000.jpg", f"s3://bucket/kyc/evidence/{UID}_1.jpg"],
)
def test_evidencia_propia_aceptada(ref):
    PaymentService._exigir_evidencia_propia(ref, UID)


@pytest.mark.parametrize(
    "ref",
    [f"kyc/evidence/{'b' * 24}_1.jpg", "products/x_1.jpg", f"users/avatars/{'b' * 24}_1.jpg", "", f"../kyc/evidence/{UID}_1.jpg"],
)
def test_evidencia_ajena_rechazada(ref):
    with pytest.raises(ValueError, match="EVIDENCE_NOT_FOUND"):
        PaymentService._exigir_evidencia_propia(ref, UID)
