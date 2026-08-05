"""Currency helpers shared by orders, payments, products and combos.

Llego opera en el mercado cubano: cada sucursal declara que moneda(s) acepta
(CUP, USD o BOTH) y, si acepta ambas, tiene su propia tasa de cambio manual.
No existe una tasa unica de mercado ni todas las sucursales aceptan ambas
monedas, asi que cualquier validacion de moneda debe hacerse contra la
configuracion de la sucursal en cuestion, nunca asumida.
"""
from typing import Optional

SUPPORTED_CURRENCIES = {"USD", "CUP"}


def normalize_currency(currency: Optional[str], fallback: str = "USD") -> str:
    """Normaliza a 'USD' o 'CUP'; cualquier otro valor cae al fallback."""
    normalized = (currency or "").strip().upper()
    if normalized in SUPPORTED_CURRENCIES:
        return normalized
    return fallback.upper()


def branch_accepts_currency(accepted_currency: Optional[str], currency: Optional[str]) -> bool:
    """True si una sucursal con `accepted_currency` (CUP/USD/BOTH) puede cobrar en `currency`."""
    accepted = (accepted_currency or "").strip().upper()
    target = normalize_currency(currency)
    if accepted == "BOTH":
        return True
    if accepted in SUPPORTED_CURRENCIES:
        return accepted == target
    # Sucursal sin acceptedCurrency configurado: comportamiento legado, solo USD.
    return target == "USD"
