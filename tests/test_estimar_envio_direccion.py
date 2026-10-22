"""estimateDeliveryFee con la dirección elegida en el carrito (latitude/longitude opcionales).

Sin coordenadas la app tenía que sobrescribir la ubicación guardada del usuario para estimar
el envío de otra dirección.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import schema.orders.queries as queries
from utils.auth import create_access_token

TOKEN = create_access_token({"user_id": "u1", "role": "customer"})


def _estimar(monkeypatch, **kwargs):
    calc = AsyncMock(return_value="estimacion")
    usuario = SimpleNamespace(location={"coordinates": [-82.3, 23.1]})
    monkeypatch.setattr(queries, "estimate_delivery_fee", calc)
    monkeypatch.setattr(queries.users_repo, "get_by_id", AsyncMock(return_value=usuario))
    resolver = queries.OrderQuery.estimate_delivery_fee
    info = SimpleNamespace(context={})
    resultado = asyncio.run(resolver(None, info, branchId="b1", jwt=TOKEN, subtotal=10, **kwargs))
    return resultado, calc


def test_sin_coordenadas_usa_la_ubicacion_guardada(monkeypatch):
    _, calc = _estimar(monkeypatch)
    assert calc.await_args.kwargs["latitude"] == 23.1
    assert calc.await_args.kwargs["longitude"] == -82.3


def test_con_coordenadas_usa_la_direccion_del_pedido(monkeypatch):
    _, calc = _estimar(monkeypatch, latitude=23.2, longitude=-82.4)
    assert calc.await_args.kwargs["latitude"] == 23.2
    assert calc.await_args.kwargs["longitude"] == -82.4


@pytest.mark.parametrize(
    "kwargs, mensaje",
    [({"latitude": 23.2}, "juntas"), ({"latitude": 123.0, "longitude": -82.0}, "no válidas")],
)
def test_coordenadas_incompletas_o_fuera_de_rango(monkeypatch, kwargs, mensaje):
    with pytest.raises(Exception, match=mensaje):
        _estimar(monkeypatch, **kwargs)
