"""Top productos con la moneda de sus ventas (null si se vendió en varias)."""
import asyncio
from datetime import datetime
from unittest.mock import patch

from repositories.orders_repository import OrderRepository


class _Cursor:
    def __init__(self, filas):
        self.filas = filas

    async def to_list(self, _):
        return self.filas


class _Coleccion:
    def __init__(self, top):
        self.top = top

    def aggregate(self, pipeline):
        if any("$unwind" in etapa for etapa in pipeline):
            return _Cursor(self.top)
        return _Cursor([])


def test_moneda_unica_o_none_si_mezcla():
    top = [
        {"_id": "p1", "name": "Pizza", "imageUrl": None, "currencies": ["CUP"], "totalQuantity": 3, "totalRevenue": 1500.0},
        {"_id": "p2", "name": "Ron", "imageUrl": None, "currencies": ["CUP", "USD"], "totalQuantity": 2, "totalRevenue": 35.5},
    ]
    repo = OrderRepository()
    with patch.object(repo, "_get_collection", return_value=_Coleccion(top)):
        stats = asyncio.run(
            repo.get_dashboard_stats("a" * 24, datetime(2026, 1, 1), datetime(2026, 12, 31))
        )
    assert [p["currency"] for p in stats["topProducts"]] == ["CUP", None]
