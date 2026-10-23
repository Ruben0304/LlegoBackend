"""Cálculo de importes con Decimal y una sola fórmula para el total de un pedido.

Antes cada camino (crear, aceptar con envío propio, modificar, reenviar y el pago) hacía su
cuenta con float y round(): el redondeo bancario sobre binario daba céntimos distintos
(round(2.675, 2) == 2.67) y el pago llegó a cobrar otra cosa que el pedido (A8). Aquí la
aritmética es exacta y el redondeo, al céntimo y hacia arriba en los medios.

Los importes se siguen guardando en Mongo y saliendo por GraphQL como float con dos
decimales: las apps publicadas no notan el cambio.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Union

Numero = Union[int, float, str, Decimal, None]

CENTIMO = Decimal("0.01")


def a_decimal(valor: Numero) -> Decimal:
    """Convierte sin arrastrar el error binario del float (str(0.1) == "0.1")."""
    if valor is None:
        return Decimal("0")
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def redondear(valor: Numero) -> float:
    """Al céntimo, con los medios hacia arriba (2.675 -> 2.68)."""
    return float(a_decimal(valor).quantize(CENTIMO, rounding=ROUND_HALF_UP))


def importe_linea(precio_unitario: Numero, cantidad: int) -> float:
    return redondear(a_decimal(precio_unitario) * cantidad)


def sumar(importes: Iterable[Numero]) -> float:
    return redondear(sum((a_decimal(i) for i in importes), Decimal("0")))


def cargo_de_servicio(subtotal: Numero, tasa: Numero) -> float:
    return redondear(a_decimal(subtotal) * a_decimal(tasa))


def total_pedido(
    subtotal: Numero, envio: Numero, cargo_servicio: Numero, descuentos: Numero = 0
) -> float:
    """subtotal + envío + cargo de servicio - descuentos, nunca negativo.

    Es la única fórmula del total: la usan el pedido (al crearlo, aceptarlo con envío propio,
    modificarlo o reenviarlo) y el intento de pago, así que lo cobrado coincide con lo mostrado.
    """
    total = a_decimal(subtotal) + a_decimal(envio) + a_decimal(cargo_servicio) - a_decimal(descuentos)
    return redondear(max(total, Decimal("0")))


def porcentaje(base: Numero, por_ciento: Numero) -> float:
    """base * por_ciento / 100 (comisiones y recargos)."""
    return redondear(a_decimal(base) * a_decimal(por_ciento) / Decimal("100"))
