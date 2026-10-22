"""Vitrinas: sin precios negativos y solo imágenes de su carpeta (A5, M3)."""
from types import SimpleNamespace

import pytest

from schema.showcases.mutations import _imagen, _items


def _item(precio):
    return SimpleNamespace(id="i1", name="Pizza", description=None, price=precio, availability=True)


def test_precio_negativo_rechazado():
    with pytest.raises(Exception, match="negativo"):
        _items([_item(10.0), _item(-1.0)])


def test_precios_validos_y_sin_precio():
    assert [i["price"] for i in _items([_item(0.0), _item(None), _item(25.5)])] == [0.0, None, 25.5]
    assert _items(None) is None


@pytest.mark.parametrize("ruta", ["products/abc_1.jpg", "users/avatars/x_1.jpg", "../showcases/a.jpg"])
def test_imagen_fuera_de_su_carpeta_rechazada(ruta):
    with pytest.raises(Exception, match="no es válida"):
        _imagen(ruta)


def test_imagen_de_vitrina_aceptada():
    assert _imagen("showcases/abc_123.jpg") == "showcases/abc_123.jpg"
    assert _imagen(None) is None
