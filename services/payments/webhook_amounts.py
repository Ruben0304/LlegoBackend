"""Comprobacion del monto recibido en los webhooks de QvaPay y TronDealer.

Antes ninguno de los dos comparaba lo recibido con lo esperado: un pago de
menos confirmaba el pedido igual y generaba el payout por lo que llegara
(context.md §12.4). Ahora, si llega menos, el pago no se completa, no se crea
payout y el pedido queda marcado para revision (requiresAttention).

La comparacion es logica pura (sin Mongo) para poder testearla directamente.
"""

import logging
import math
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Tolerancia de redondeo: los montos van en USD/USDT con 2 decimales, asi que
# se acepta hasta un centavo de diferencia.
AMOUNT_TOLERANCE = 0.01


def parse_amount(raw: Any) -> Optional[float]:
    """Monto del webhook como float finito, o None si no se puede interpretar."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def is_underpaid(
    received: Optional[float],
    expected: float,
    tolerance: float = AMOUNT_TOLERANCE,
) -> bool:
    """True si llego menos de lo esperado (mas alla de la tolerancia) o si el
    monto recibido es ilegible. Se redondea a centavos para no depender de
    errores de coma flotante (25.00 - 24.99 no es exactamente 0.01)."""
    if received is None or not math.isfinite(received):
        return True
    shortfall = round(float(expected) - float(received), 2)
    return shortfall > tolerance


def underpayment_reason(
    gateway: str,
    received: Optional[float],
    expected: float,
    reference: str,
) -> str:
    """Motivo legible para soporte (va a Order.attentionReason)."""
    received_txt = f"{received:.2f}" if received is not None else "un monto ilegible"
    return (
        f"Pago {gateway} incompleto: llegaron {received_txt} de {expected:.2f} "
        f"esperados (ref {reference}). No se marco como pagado ni se genero "
        "payout: revisar y completar o reembolsar a mano."
    )


async def flag_underpaid_order(order_id: str, reason: str) -> None:
    """Marca el pedido para revision sin tocar su estado ni su paymentStatus.

    Se quita el deadline para que el worker de timeout no lo cancele mientras
    soporte decide: el cliente ya puso dinero.
    """
    from domain.orders import OrderActor, OrderTimeline
    from repositories import orders_repo

    order = await orders_repo.get_by_id(order_id)
    timeline_entry = None
    if order is not None:
        timeline_entry = OrderTimeline(
            status=order.status,
            timestamp=datetime.utcnow(),
            message=(
                "Recibimos un pago menor al total del pedido. "
                "Soporte ya fue avisado y revisara tu caso"
            ),
            actor=OrderActor.SYSTEM,
        )
    flagged = await orders_repo.mark_requires_attention(
        order_id,
        reason,
        timeline_entry=timeline_entry,
        clear_deadline=True,
    )
    if flagged is None:
        logger.error(
            "No se pudo marcar para revision el pedido %s (pago incompleto): %s",
            order_id,
            reason,
        )
