"""Provider-agnostic order/payment helpers.

Extracted from PaymentService so that both PaymentService itself and the
digital payment providers (services/payments/providers/) can reuse them
without one importing the other.
"""

from datetime import datetime
from typing import Optional

from bson import ObjectId

from clients.mongodb_client import get_database


def to_object_id(value: Optional[str]):
    if value is None:
        return None
    try:
        return ObjectId(value)
    except Exception:
        return value


async def get_order(order_id: str) -> Optional[dict]:
    """Get an order document by ID."""
    db = get_database()
    try:
        doc = await db.orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        doc = await db.orders.find_one({"_id": order_id})
    return doc


async def get_payment_method(payment_method_id: str) -> Optional[dict]:
    """Get a payment method document by ID."""
    db = get_database()
    try:
        doc = await db.payment_methods.find_one({"_id": ObjectId(payment_method_id)})
    except Exception:
        doc = await db.payment_methods.find_one({"_id": payment_method_id})
    return doc


async def get_branch(branch_id: str) -> Optional[dict]:
    """Get a branch document (as dict) by ID using the branch repository."""
    from repositories import branches_repo

    branch = await branches_repo.get_by_id(branch_id)
    return branch.model_dump() if branch else None


async def update_order_payment_attempt(order_id: str, attempt_id: str) -> None:
    """Record the current payment attempt ID on the order."""
    db = get_database()
    try:
        order_id_obj = ObjectId(order_id)
    except Exception:
        order_id_obj = order_id

    await db.orders.update_one(
        {"_id": order_id_obj},
        {
            "$set": {
                "currentPaymentAttemptId": attempt_id,
                "updatedAt": datetime.utcnow(),
            }
        },
    )


async def complete_order_payment(order_id: str, attempt_id: str) -> None:
    """Mark an order's payment as completed and advance its status.

    La logica de estados vive en OrderService.mark_order_paid: avanza a
    ACCEPTED con plazo nuevo solo si el pedido esperaba el pago, y si no (p. ej.
    ya cancelado) registra el pago y marca el pedido para reembolso.
    """
    from services.orders_service import order_service

    await order_service.mark_order_paid(str(order_id), str(attempt_id))
