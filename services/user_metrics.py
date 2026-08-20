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


# Segment keys shared by the metrics cards and the drill-down list, so tapping
# a card can't diverge from the number printed on it.
SEGMENT_ALL = "all"
SEGMENT_ACTIVE = "active"
SEGMENT_NEW = "new"
SEGMENT_CUSTOMERS_ONLY = "customers_only"
SEGMENT_COURIERS = "couriers"
SEGMENT_BUSINESSES = "businesses"


def build_segment_spec(
    segment: str,
    *,
    courier_ids: Set[str],
    business_ids: Set[str],
    active_ids: Set[str],
) -> Dict[str, Any]:
    """Describe which users a segment card contains, as an include/exclude spec.

    Kept separate from the repository (and free of Mongo types) so the mapping
    from "card the admin tapped" to "set of users" is testable on its own — the
    list must match the count shown on the card exactly.
    """
    non_customers = courier_ids | business_ids

    if segment == SEGMENT_COURIERS:
        return {"include_ids": set(courier_ids), "exclude_ids": None, "only_new": False}
    if segment == SEGMENT_BUSINESSES:
        return {"include_ids": set(business_ids), "exclude_ids": None, "only_new": False}
    if segment == SEGMENT_CUSTOMERS_ONLY:
        return {"include_ids": None, "exclude_ids": set(non_customers), "only_new": False}
    if segment == SEGMENT_ACTIVE:
        return {"include_ids": set(active_ids), "exclude_ids": None, "only_new": False}
    if segment == SEGMENT_NEW:
        return {"include_ids": None, "exclude_ids": None, "only_new": True}
    # SEGMENT_ALL and anything unrecognised: no restriction.
    return {"include_ids": None, "exclude_ids": None, "only_new": False}
