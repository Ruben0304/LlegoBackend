"""Plan de la migración de correos a minúsculas: los choques no se tocan."""
from scripts.migrar_correos_minusculas import planificar


def test_cambia_los_que_tienen_mayusculas_y_aparta_los_choques():
    usuarios = [
        {"_id": 1, "email": "Ana@Correo.com"},
        {"_id": 2, "email": "luis@correo.com"},
        {"_id": 3, "email": "Pepe@correo.com"},
        {"_id": 4, "email": "pepe@correo.com"},
        {"_id": 5, "email": ""},
    ]

    cambios, choques = planificar(usuarios)

    assert cambios == [(1, "ana@correo.com")]
    assert choques == {"pepe@correo.com": ["3", "4"]}
