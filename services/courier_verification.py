"""Validación pura de los datos de alta de un mensajero (sin Mongo)."""

import re
from datetime import date
from typing import Tuple

_NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]+$")
_NAME_MAX = 50
REJECTION_REASON_MAX = 300


def _normalize_name(value: str, label: str) -> str:
    cleaned = " ".join((value or "").split())
    if len(cleaned) < 2:
        raise ValueError(f"El {label} es obligatorio")
    if len(cleaned) > _NAME_MAX:
        raise ValueError(f"El {label} no puede superar {_NAME_MAX} caracteres")
    if not _NAME_RE.match(cleaned):
        raise ValueError(f"El {label} solo puede contener letras")
    return cleaned


def normalize_identity_card(value: str) -> str:
    """Carnet de identidad cubano: 11 dígitos, los 6 primeros son AAMMDD."""
    digits = re.sub(r"\s", "", value or "")
    if not re.fullmatch(r"\d{11}", digits):
        raise ValueError("El carnet de identidad debe tener 11 dígitos")
    month, day = int(digits[2:4]), int(digits[4:6])
    try:
        # 2000 es bisiesto: acepta cualquier 29/02 sin saber el siglo.
        date(2000, month, day)
    except ValueError:
        raise ValueError("El carnet de identidad no es válido")
    return digits


def normalize_courier_profile(
    first_name: str, last_name: str, identity_card: str
) -> Tuple[str, str, str]:
    return (
        _normalize_name(first_name, "nombre"),
        _normalize_name(last_name, "apellido"),
        normalize_identity_card(identity_card),
    )


def normalize_rejection_reason(reason: str) -> str:
    cleaned = " ".join((reason or "").split())
    if not cleaned:
        raise ValueError("Indica el motivo del rechazo")
    return cleaned[:REJECTION_REASON_MAX]
