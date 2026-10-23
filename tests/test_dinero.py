"""utils/dinero: aritmética exacta y una sola fórmula de total."""
from utils.dinero import (
    a_decimal,
    cargo_de_servicio,
    importe_linea,
    porcentaje,
    redondear,
    sumar,
    total_pedido,
)


def test_redondeo_al_centimo_con_medios_hacia_arriba():
    assert round(2.675, 2) == 2.67  # el problema: float binario + redondeo bancario
    assert redondear(2.675) == 2.68
    assert redondear(0.125) == 0.13
    assert redondear(1.005) == 1.01


def test_sumas_sin_error_binario():
    assert 0.1 + 0.2 != 0.3
    assert sumar([0.1, 0.2]) == 0.3
    assert sumar([19.99] * 3) == 59.97
    assert a_decimal(None) == 0


def test_lineas_y_cargo_de_servicio():
    assert importe_linea(19.99, 3) == 59.97
    assert cargo_de_servicio(1150, 0.1) == 115.0
    assert cargo_de_servicio(33.35, 0.1) == 3.34  # 3.335 -> 3.34, no 3.33


def test_total_pedido_y_nunca_negativo():
    assert total_pedido(1150, 700, 115, 0) == 1965.0
    assert total_pedido(10.10, 0.20, 1.01, 0.31) == 11.0
    assert total_pedido(10, 0, 0, 50) == 0.0


def test_porcentaje():
    assert porcentaje(1965, 2.5) == 49.13
    assert porcentaje(100, 0) == 0.0


def test_el_pago_cobra_lo_mismo_que_el_total_del_pedido():
    """Una sola fórmula: el intento de pago (sin comisión) coincide con order.total."""
    from services.payments_service import PaymentService

    subtotal = 33.35
    envio = 12.345
    cargo = cargo_de_servicio(subtotal, 0.1)
    pedido = {
        "subtotal": subtotal,
        "deliveryFee": envio,
        "serviceCharge": cargo,
        "discounts": [{"amount": 0.105}],
        "total": total_pedido(subtotal, envio, cargo, 0.105),
    }
    metodo = {"currency": "CUP", "method": "transfer", "commissionPercent": 0}
    *_, total, _moneda = PaymentService()._calculate_amounts(pedido, metodo)
    assert total == pedido["total"]
