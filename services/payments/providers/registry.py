"""Registro de proveedores de pago digital (Grupo A).

ALL_DIGITAL_PROVIDERS: todos los proveedores implementados, siempre
presentes. Lo usan los webhooks y los refunds — un pago viejo de un
proveedor hoy dormido debe poder seguir resolviéndose.

DIGITAL_PAYMENT_PROVIDERS: subconjunto que initiate_payment() y la query
`paymentMethods` realmente pueden usar para arrancar pagos NUEVOS. Hoy está
vacío a propósito (ver ENABLED_DIGITAL_PROVIDER_CODES) — stripe/qvapay/
trondealer quedan implementados pero dormidos.

Para "despertar" un proveedor: agregar su código a
ENABLED_DIGITAL_PROVIDER_CODES aquí, y agregar su `method` a
ENABLED_PAYMENT_METHOD_TYPES en services/payments/enabled_methods.py. Nada
más debería requerir cambios.
"""

from typing import Dict

from services.payments.providers.base import DigitalPaymentProvider
from services.payments.providers.qvapay_provider import QvaPayProvider
from services.payments.providers.stripe_provider import StripeProvider
from services.payments.providers.trondealer_provider import TronDealerProvider

ALL_DIGITAL_PROVIDERS: Dict[str, DigitalPaymentProvider] = {
    "stripe": StripeProvider(),
    "qvapay": QvaPayProvider(),
    # Clave = PaymentMethod.method ("usdt"), no el nombre del proveedor.
    "usdt": TronDealerProvider(),
}

# Dormant a propósito: cash y transfer son los únicos métodos activos por
# ahora (ver services/payments/enabled_methods.py). stripe/qvapay/trondealer
# quedan completamente implementados y listos, solo no registrados como
# "iniciables" todavía.
ENABLED_DIGITAL_PROVIDER_CODES: set[str] = set()

DIGITAL_PAYMENT_PROVIDERS: Dict[str, DigitalPaymentProvider] = {
    code: provider
    for code, provider in ALL_DIGITAL_PROVIDERS.items()
    if code in ENABLED_DIGITAL_PROVIDER_CODES
}
