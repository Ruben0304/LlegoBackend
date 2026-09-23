"""Common contract for Grupo A: proveedores de pago digital externos.

stripe, qvapay, trondealer y (a futuro) tropipay comparten el mismo ciclo de
vida: initiate → el cliente presenta algo al usuario (sheet nativo, redirect,
address) → se confirma de forma async (webhook/polling) → se liquida el
PaymentAttempt.

Lo que NO se estandariza aquí es el settlement: stripe/wallet acreditan el
wallet interno de Llego, mientras que qvapay/trondealer disparan un payout
externo (services/payout_repository). Esa diferencia es una decisión de
negocio real, no duplicación accidental — cada provider concreto es libre de
resolverla como corresponda dentro de handle_confirmed_event/refund.

Grupo B (wallet, transfer, cash) NO implementa este protocolo: son
liquidaciones manuales/internas con su propia forma, no "otro proveedor más".
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from domain.payments import PaymentAttempt


class NotSupportedError(Exception):
    """Un provider no soporta la operación pedida (p. ej. refund)."""


class DigitalPaymentProvider(ABC):
    """Un proveedor de pago digital externo (Grupo A)."""

    #: Debe matchear `PaymentMethod.method` en Mongo (p. ej. "stripe").
    method_code: str

    @abstractmethod
    async def initiate(
        self,
        payment_attempt: PaymentAttempt,
        order: dict,
        payment_method: dict,
        user_id: str,
    ) -> PaymentAttempt:
        """Arranca el pago con el proveedor y puebla providerReference/providerPayload
        (y el status correspondiente) en payment_attempt. No persiste el intento —
        eso lo hace el caller (PaymentService.initiate_payment), igual que hoy."""
        raise NotImplementedError

    @abstractmethod
    async def handle_confirmed_event(self, event: Dict[str, Any]) -> PaymentAttempt:
        """Procesa un evento ya verificado/parseado del proveedor (webhook) y
        liquida el PaymentAttempt correspondiente. La forma de `event` es
        específica de cada proveedor — quien lo llama (el endpoint HTTP) es
        responsable de la verificación de firma y del parseo inicial."""
        raise NotImplementedError

    async def refund(self, payment_attempt: PaymentAttempt) -> PaymentAttempt:
        """Reembolsa un pago completado. Default: no soportado — no todos los
        proveedores lo necesitan desde el día uno."""
        raise NotSupportedError(
            f"El proveedor '{self.method_code}' no soporta reembolsos todavía"
        )
