"""Pure segmentation logic for the admin user metrics.

Lives outside the repository on purpose: the set arithmetic is the part worth
testing, and keeping it free of Mongo makes that possible without a live or
mocked database — same reasoning as services/orders_utils.compute_fee_recommendation.

Why segments are computed by joins instead of read off the user document:
`User.role` is hardcoded to "customer" at registration (repositories/auth_repository.py)
and there is no mutation to change it, so every user of all three apps carries
the same role. App membership is therefore derived — a user has a
`delivery_persons` record (courier), or owns/manages a business (business), or
neither (customer-only).
"""

from typing import Any, Dict, Set


def compute_user_segments(
    *,
    total_users: int,
    courier_ids: Set[str],
    business_ids: Set[str],
    active_ids: Set[str],
) -> Dict[str, Any]:
    """Break the user base into app segments, with overlap made explicit.

    Args:
        total_users: every registered user.
        courier_ids: users with a delivery_persons record (AppMensajeros).
        business_ids: users who own or manage a business (LlegoBusiness).
        active_ids: users considered active in the window.

    A user can belong to several segments at once — the model allows it and it
    happens — so `couriers` and `businesses` overlap. `customersOnly` is the
    remainder, which keeps the three totals summing to `total_users` while
    `multiRoleUsers` surfaces the intersection that would otherwise be invisible.
    """
    both = courier_ids & business_ids
    non_customers = courier_ids | business_ids

    # Guard against drift: a delivery_persons or businesses document can
    # reference a user that no longer exists (deletion is a hard delete, with
    # no tombstone), which would otherwise push this negative.
    customers_only_total = max(total_users - len(non_customers), 0)
    customers_only_active = len(active_ids - non_customers)

    return {
        "totalUsers": total_users,
        "activeUsers": len(active_ids),
        "customersOnly": {
            "total": customers_only_total,
            "active": min(customers_only_active, customers_only_total),
        },
        "couriers": {
            "total": len(courier_ids),
            "active": len(active_ids & courier_ids),
        },
        "businesses": {
            "total": len(business_ids),
            "active": len(active_ids & business_ids),
        },
        "multiRoleUsers": len(both),
    }
