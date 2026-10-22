"""M13: los campos de un listado de pedidos se cargan en lote (antes 24 pedidos = 77 consultas)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from schema.orders import types as order_types


def test_usa_el_dataloader_del_contexto_y_no_la_consulta_suelta():
    loader = SimpleNamespace(load=AsyncMock(return_value="cliente"))
    suelta = AsyncMock()
    info = SimpleNamespace(context={"user_loader": loader})

    assert asyncio.run(order_types._cargar(info, "user_loader", 123, suelta)) == "cliente"
    loader.load.assert_awaited_once_with("123")
    suelta.assert_not_awaited()


def test_sin_dataloader_hace_la_consulta_suelta():
    suelta = AsyncMock(return_value="cliente")
    info = SimpleNamespace(context={})

    assert asyncio.run(order_types._cargar(info, "user_loader", "u1", suelta)) == "cliente"
    suelta.assert_awaited_once_with("u1")
