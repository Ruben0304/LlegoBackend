"""Campañas pagadas por transferencia: un admin confirma el pago; Stripe no está conectado."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import services.ads_service as ads_module

servicio = ads_module.ads_service


@pytest.fixture
def repo(monkeypatch):
    update = AsyncMock(side_effect=lambda cid, cambios: SimpleNamespace(id=cid, **cambios))
    monkeypatch.setattr(ads_module.ad_campaigns_repo, "update", update)
    return update


def _metodo(monkeypatch, tipo):
    monkeypatch.setattr(
        ads_module.payment_methods_repo, "get_by_id", AsyncMock(return_value=SimpleNamespace(method=tipo))
    )


def test_transferencia_queda_esperando_comprobante(monkeypatch, repo):
    _metodo(monkeypatch, "transfer")
    campana = SimpleNamespace(id="c1")
    resultado = asyncio.run(servicio.purchase_campaign(campana, "pm1"))
    assert resultado.status == "pending_payment" and resultado.paymentStatus == "pending_proof"


def test_stripe_se_rechaza_en_vez_de_quedar_colgada(monkeypatch, repo):
    _metodo(monkeypatch, "stripe")
    with pytest.raises(Exception, match="billetera de la sucursal o por transferencia"):
        asyncio.run(servicio.purchase_campaign(SimpleNamespace(id="c1"), "pm1"))
    repo.assert_not_awaited()


def test_admin_confirma_la_transferencia_y_pasa_a_revision(repo):
    campana = SimpleNamespace(id="c1", status="pending_payment", paymentStatus="pending_proof")
    resultado = asyncio.run(servicio.confirm_transfer_payment(campana, " TM123 "))
    assert resultado.paymentStatus == "paid" and resultado.status == "pending_review"
    assert resultado.paymentRef == "TM123"


def test_no_se_confirma_una_campana_que_no_espera_transferencia(repo):
    campana = SimpleNamespace(id="c1", status="draft", paymentStatus="unpaid")
    with pytest.raises(Exception, match="no está esperando"):
        asyncio.run(servicio.confirm_transfer_payment(campana))
