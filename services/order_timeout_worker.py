"""Background worker helpers for order pre-preparation timeouts."""

from services.orders_service import order_service


async def expire_order_deadlines(limit: int = 100) -> int:
    """
    Auto-cancel orders whose pre-preparation SLA deadline has elapsed.

    Returns:
        Number of orders cancelled by timeout in this execution.
    """
    return await order_service.expire_stale_pre_preparation_orders(limit=limit)

