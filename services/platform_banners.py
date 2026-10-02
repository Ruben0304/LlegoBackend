"""Lógica pura de los banners de plataforma (sin Mongo ni Strawberry).

Validación de lo que manda el panel admin y la URL de acción que reciben las
apps cliente (`actionUrl`). Mismo criterio que `services/branch_hours.py`:
funciones testeables aisladas.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from domain.platform_banners import PLATFORM_BANNER_APP_TARGETS
from utils.phone import CUBA_COUNTRY_CODE, cuban_national_number

WHATSAPP_URL_PREFIX = "https://wa.me/"


def whatsapp_digits(value: Optional[str]) -> Optional[str]:
    """Número de WhatsApp en el formato de wa.me: solo dígitos, con código de país.

    Un número cubano en cualquier formato habitual ("5XXXXXXX", "+53 5XXX XXXX")
    sale como "535XXXXXXX". Otro número internacional ("+1 305 ...") conserva
    su código. None si no hay número utilizable.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    national = cuban_national_number(raw)
    if national:
        return f"{CUBA_COUNTRY_CODE}{national}"
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    # E.164: entre 8 y 15 dígitos con el código de país.
    if 8 <= len(digits) <= 15:
        return digits
    return None


def banner_action_url(whatsapp: Optional[str], link: Optional[str]) -> Optional[str]:
    """URL a abrir al tocar el banner: wa.me si hay WhatsApp, si no el link.

    None si no hay acción externa (el banner puede abrir una tienda por
    `branchId`, que las apps priorizan sobre esta URL).
    """
    digits = whatsapp_digits(whatsapp)
    if digits:
        return f"{WHATSAPP_URL_PREFIX}{digits}"
    cleaned = (link or "").strip()
    return cleaned or None


def normalize_banner_link(link: Optional[str]) -> Optional[str]:
    """Valida el link externo del banner. Vacío → None. Lanza ValueError si no es http(s)."""
    cleaned = (link or "").strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("El enlace del banner debe ser una URL http(s) completa")
    return cleaned


def normalize_banner_whatsapp(whatsapp: Optional[str]) -> Optional[str]:
    """Valida el WhatsApp del banner. Vacío → None. Lanza ValueError si no es un número."""
    if not (whatsapp or "").strip():
        return None
    if whatsapp_digits(whatsapp) is None:
        raise ValueError("El WhatsApp del banner debe ser un número de teléfono válido")
    return whatsapp.strip()


def validate_app_target(app_target: str) -> str:
    target = (app_target or "").strip()
    if target not in PLATFORM_BANNER_APP_TARGETS:
        raise ValueError(
            "appTarget debe ser uno de: " + ", ".join(PLATFORM_BANNER_APP_TARGETS)
        )
    return target


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """GraphQL puede entregar fechas aware; Mongo y el resto del backend usan UTC naive."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def validate_window(start_at: Optional[datetime], end_at: Optional[datetime]) -> None:
    """La ventana de publicación, si tiene las dos fechas, debe ser creciente."""
    if start_at is None or end_at is None:
        return
    if to_naive_utc(end_at) <= to_naive_utc(start_at):
        raise ValueError("La fecha de fin debe ser posterior a la de inicio")
