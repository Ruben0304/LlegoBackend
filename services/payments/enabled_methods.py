"""Single source of truth for which payment method types are currently live.

A method type not in this set is fully implemented (provider class, GraphQL
plumbing, webhook handling) but dormant: it won't be returned by the
`paymentMethods` query and `initiate_payment()` will refuse to start it.

To "wake up" a method later: add its `method` string here, and — if it's a
Grupo A digital provider (stripe/qvapay/trondealer/tropipay) — also add its
code to ENABLED_DIGITAL_PROVIDER_CODES in
services/payments/providers/registry.py. Nothing else needs to change.
"""

ENABLED_PAYMENT_METHOD_TYPES: set[str] = {"cash", "transfer", "transfermovil"}
