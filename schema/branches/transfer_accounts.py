"""Helpers for branch transfer account normalization and QR generation."""

import re
from typing import Any, Dict, List, Optional

QR_PREFIX = "TRANSFERMOVIL_ETECSA,TRANSFERENCIA"


def _only_digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_card_number(value: Optional[str], strict: bool = True) -> Optional[str]:
    """Normalize card number to digits only and validate expected length."""
    digits = _only_digits(value)
    if len(digits) == 16:
        return digits

    if strict:
        raise Exception("cardNumber debe tener exactamente 16 dígitos")
    return digits or None


def normalize_confirm_phone(value: Optional[str], strict: bool = True) -> Optional[str]:
    """Normalize Cuban mobile number used for transfer confirmation."""
    digits = _only_digits(value)

    # Accept +53XXXXXXXX or 53XXXXXXXX and normalize to local 8 digits.
    if len(digits) == 10 and digits.startswith("53"):
        digits = digits[2:]

    if len(digits) == 8:
        return digits

    if strict:
        raise Exception(
            "confirmPhone debe tener 8 dígitos (se acepta prefijo +53 y se normaliza)"
        )
    return digits or None


def normalize_holder_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = value.strip()
    return clean or None


def build_pago_qr(card_number: str, confirm_phone: str) -> str:
    """Build Transfermóvil QR payload in the agreed format."""
    return f"{QR_PREFIX},{card_number},{confirm_phone},"


def normalize_transfer_accounts(raw_accounts: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Normalize and validate transfer accounts from GraphQL input objects."""
    normalized: List[Dict[str, Any]] = []
    for account in raw_accounts or []:
        card_number = normalize_card_number(getattr(account, "cardNumber", None), strict=True)
        confirm_phone = normalize_confirm_phone(
            getattr(account, "confirmPhone", None), strict=True
        )
        holder_name = normalize_holder_name(getattr(account, "cardHolderName", None))
        is_active = bool(getattr(account, "isActive", True))

        normalized.append(
            {
                "cardNumber": card_number,
                "confirmPhone": confirm_phone,
                "cardHolderName": holder_name,
                "isActive": is_active,
            }
        )
    return normalized


def build_legacy_qr_payments(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create qrPayments documents from normalized transfer accounts."""
    return [
        {
            "value": build_pago_qr(a["cardNumber"], a["confirmPhone"]),
            "image": None,
            "isActive": bool(a.get("isActive", True)),
        }
        for a in accounts
        if a.get("cardNumber") and a.get("confirmPhone")
    ]


def build_legacy_phones(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create phones documents from normalized transfer accounts."""
    return [
        {"phone": a["confirmPhone"], "isActive": bool(a.get("isActive", True))}
        for a in accounts
        if a.get("confirmPhone")
    ]

