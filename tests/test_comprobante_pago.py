"""Comprobantes de pago: se guarda la ruta (no una URL firmada que caduca) y solo de su carpeta."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from domain.payments import PaymentAttempt, PaymentAttemptStatus
from schema.payments import types as payment_types
from services.payments_service import PaymentService

CLIENTE = str(ObjectId())


def _servicio(monkeypatch):
    intento = PaymentAttempt(
        _id=str(ObjectId()), orderId=str(ObjectId()), paymentMethodId=str(ObjectId()),
        subtotal=100.0, deliveryFee=0.0, commissionAmount=0.0, totalAmount=100.0,
        currency="local", status=PaymentAttemptStatus.AWAITING_PROOF,
    )
    servicio = PaymentService()
    servicio.payment_attempts_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=intento), set_proof=AsyncMock(return_value=intento)
    )
    servicio._get_order = AsyncMock(
        return_value={"_id": intento.orderId, "customerId": CLIENTE, "status": "pending_payment"}
    )
    return servicio, intento


@pytest.mark.parametrize("ruta", ["products/abc_1.jpg", "users/avatars/x_1.jpg", "../payments/proofs/a.jpg"])
def test_ruta_ajena_rechazada(monkeypatch, ruta):
    servicio, intento = _servicio(monkeypatch)
    with pytest.raises(ValueError, match="comprobante no es válido"):
        asyncio.run(servicio.confirm_payment_sent(str(intento.id), CLIENTE, ruta))
    servicio.payment_attempts_repo.set_proof.assert_not_awaited()


def test_el_tipo_firma_la_ruta_al_leerla_y_deja_las_urls_antiguas(monkeypatch):
    monkeypatch.setattr(
        payment_types, "generate_presigned_url",
        lambda clave: clave if clave.startswith("http") else f"https://firmada/{clave}",
    )
    _, intento = _servicio(monkeypatch)
    intento.proofUrl = "payments/proofs/abc_1.jpg"
    assert payment_types.payment_attempt_to_type(intento).proofUrl == "https://firmada/payments/proofs/abc_1.jpg"
    intento.proofUrl = "https://antigua/x.jpg"
    assert payment_types.payment_attempt_to_type(intento).proofUrl == "https://antigua/x.jpg"
