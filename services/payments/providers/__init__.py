"""Grupo A: proveedores de pago digital externos (stripe, qvapay, trondealer,
futuro tropipay) detrás de un contrato común. Ver base.py y registry.py."""

from services.payments.providers.base import DigitalPaymentProvider, NotSupportedError
from services.payments.providers.registry import (
    ALL_DIGITAL_PROVIDERS,
    DIGITAL_PAYMENT_PROVIDERS,
    ENABLED_DIGITAL_PROVIDER_CODES,
)

__all__ = [
    "DigitalPaymentProvider",
    "NotSupportedError",
    "ALL_DIGITAL_PROVIDERS",
    "DIGITAL_PAYMENT_PROVIDERS",
    "ENABLED_DIGITAL_PROVIDER_CODES",
]
