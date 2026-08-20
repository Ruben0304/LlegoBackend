"""Unit tests for the admin user metrics.

Same convention as tests/test_admin_orders_queries.py: the pure segmentation
function is tested directly, and the resolver is tested against mocked
repositories — no live or mocked MongoDB.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.extensions as extensions
import schema.users.queries as queries
from services.user_metrics import build_segment_spec, compute_user_segments


# ---------------------------------------------------------------------------
# compute_user_segments (pure)
# ---------------------------------------------------------------------------


def test_segments_with_no_users_are_all_zero():
    result = compute_user_segments(
        total_users=0, courier_ids=set(), business_ids=set(), active_ids=set()
    )
    assert result["totalUsers"] == 0
    assert result["activeUsers"] == 0
    assert result["customersOnly"] == {"total": 0, "active": 0}
    assert result["couriers"] == {"total": 0, "active": 0}
    assert result["businesses"] == {"total": 0, "active": 0}
    assert result["multiRoleUsers"] == 0


def test_segment_totals_sum_to_total_users():
    # 10 users: 2 couriers, 3 business (1 of them also a courier) => 6 pure customers.
    result = compute_user_segments(
        total_users=10,
        courier_ids={"c1", "c2"},
        business_ids={"b1", "b2", "c2"},
        active_ids=set(),
    )
    union = len({"c1", "c2", "b1", "b2"})
    assert result["customersOnly"]["total"] == 10 - union == 6
    assert result["couriers"]["total"] == 2
    assert result["businesses"]["total"] == 3
    assert result["customersOnly"]["total"] + union == 10


def test_multi_role_counts_the_intersection_once():
    result = compute_user_segments(
        total_users=5,
        courier_ids={"u1", "u2"},
        business_ids={"u1", "u2", "u3"},
        active_ids=set(),
    )
    assert result["multiRoleUsers"] == 2


def test_active_users_split_across_overlapping_segments():
    # u1 is both courier and business, so it counts as active in both.
    result = compute_user_segments(
        total_users=4,
        courier_ids={"u1", "u2"},
        business_ids={"u1", "u3"},
        active_ids={"u1", "u4"},
    )
    assert result["activeUsers"] == 2
    assert result["couriers"]["active"] == 1
    assert result["businesses"]["active"] == 1
    # u4 belongs to no segment, so it is an active customer-only user.
    assert result["customersOnly"]["active"] == 1


def test_customers_only_never_goes_negative_on_stale_references():
    """A delivery_persons/business doc can point at a deleted user (hard delete,
    no tombstone), which would otherwise push the remainder below zero."""
    result = compute_user_segments(
        total_users=1,
        courier_ids={"ghost1", "ghost2", "ghost3"},
        business_ids=set(),
        active_ids=set(),
    )
    assert result["customersOnly"]["total"] == 0


def test_customers_only_active_is_capped_by_its_total():
    result = compute_user_segments(
        total_users=1,
        courier_ids={"ghost1", "ghost2"},
        business_ids=set(),
        active_ids={"a1", "a2", "a3"},
    )
    assert result["customersOnly"]["active"] <= result["customersOnly"]["total"]


# ---------------------------------------------------------------------------
# admin_user_metrics resolver
# ---------------------------------------------------------------------------


def test_admin_user_metrics_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception(f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}")

    monkeypatch.setattr(queries, "require_role", _deny)
    sources = AsyncMock()
    monkeypatch.setattr(queries.users_repo, "get_metrics_sources", sources)

    query = queries.UserQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(query.admin_user_metrics(info=None, jwt="token"))
    sources.assert_not_awaited()


def test_admin_user_metrics_builds_type_from_sources(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    monkeypatch.setattr(
        queries.users_repo,
        "get_metrics_sources",
        AsyncMock(
            return_value={
                "total_users": 10,
                "new_users": 3,
                "courier_ids": {"c1", "c2"},
                "business_ids": {"b1", "c2"},
                "active_ids": {"c1", "b1", "x9"},
            }
        ),
    )
    monkeypatch.setattr(
        queries.users_repo,
        "get_signups_by_day",
        AsyncMock(return_value=[{"day": "2026-08-18", "count": 2}]),
    )

    query = queries.UserQuery()
    result = asyncio.run(
        query.admin_user_metrics(info=None, jwt="token", activeDays=7)
    )

    assert result.totalUsers == 10
    assert result.activeUsers == 3
    assert result.newUsersInPeriod == 3
    assert result.couriers.total == 2
    assert result.businesses.total == 2
    assert result.multiRoleUsers == 1
    assert result.activeDays == 7
    assert result.signupsByDay[0].day == "2026-08-18"


def test_admin_user_metrics_clamps_non_positive_window(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    monkeypatch.setattr(
        queries.users_repo,
        "get_metrics_sources",
        AsyncMock(
            return_value={
                "total_users": 0,
                "new_users": 0,
                "courier_ids": set(),
                "business_ids": set(),
                "active_ids": set(),
            }
        ),
    )
    monkeypatch.setattr(
        queries.users_repo, "get_signups_by_day", AsyncMock(return_value=[])
    )

    query = queries.UserQuery()
    result = asyncio.run(query.admin_user_metrics(info=None, jwt="t", activeDays=0))
    assert result.activeDays == 1


# ---------------------------------------------------------------------------
# LastSeenExtension throttle
# ---------------------------------------------------------------------------


def _extension_with_context(context):
    ext = extensions.LastSeenExtension.__new__(extensions.LastSeenExtension)
    ext.execution_context = SimpleNamespace(context=context, result=None)
    return ext


def test_last_seen_does_nothing_without_user_id(monkeypatch):
    extensions._LAST_SEEN_WRITES.clear()
    touched = []
    monkeypatch.setattr(
        extensions.LastSeenExtension, "_touch_last_seen", AsyncMock(side_effect=touched.append)
    )

    _extension_with_context({}).on_request_end()
    assert extensions._LAST_SEEN_WRITES == {}


def test_last_seen_writes_once_within_throttle_window(monkeypatch):
    extensions._LAST_SEEN_WRITES.clear()
    calls = []
    monkeypatch.setattr(
        extensions.asyncio, "create_task", lambda coro: (coro.close(), calls.append(1))
    )

    ext = _extension_with_context({"user_id": "u1"})
    ext.on_request_end()
    ext.on_request_end()
    ext.on_request_end()

    assert len(calls) == 1, "throttle must collapse repeated requests into one write"
    assert "u1" in extensions._LAST_SEEN_WRITES


def test_last_seen_tracks_each_user_separately(monkeypatch):
    extensions._LAST_SEEN_WRITES.clear()
    calls = []
    monkeypatch.setattr(
        extensions.asyncio, "create_task", lambda coro: (coro.close(), calls.append(1))
    )

    _extension_with_context({"user_id": "u1"}).on_request_end()
    _extension_with_context({"user_id": "u2"}).on_request_end()

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# build_segment_spec (pure) — the list behind a card must match its count
# ---------------------------------------------------------------------------

COURIERS = {"c1", "c2"}
BUSINESSES = {"b1", "c2"}
ACTIVES = {"c1", "b1", "x9"}


def _spec(segment):
    return build_segment_spec(
        segment, courier_ids=COURIERS, business_ids=BUSINESSES, active_ids=ACTIVES
    )


def test_spec_all_has_no_restriction():
    spec = _spec("all")
    assert spec == {"include_ids": None, "exclude_ids": None, "only_new": False}


def test_spec_couriers_includes_exactly_the_courier_set():
    assert _spec("couriers")["include_ids"] == COURIERS


def test_spec_businesses_includes_exactly_the_business_set():
    assert _spec("businesses")["include_ids"] == BUSINESSES


def test_spec_customers_only_excludes_the_union():
    spec = _spec("customers_only")
    assert spec["include_ids"] is None
    assert spec["exclude_ids"] == COURIERS | BUSINESSES


def test_spec_active_includes_the_active_set():
    assert _spec("active")["include_ids"] == ACTIVES


def test_spec_new_filters_by_date_only():
    spec = _spec("new")
    assert spec["only_new"] is True
    assert spec["include_ids"] is None


def test_spec_segment_sizes_match_the_card_counts():
    """Guard against the list and the metric card drifting apart."""
    total_users = 10
    metrics = compute_user_segments(
        total_users=total_users,
        courier_ids=COURIERS,
        business_ids=BUSINESSES,
        active_ids=ACTIVES,
    )
    assert len(_spec("couriers")["include_ids"]) == metrics["couriers"]["total"]
    assert len(_spec("businesses")["include_ids"]) == metrics["businesses"]["total"]
    assert (
        total_users - len(_spec("customers_only")["exclude_ids"])
        == metrics["customersOnly"]["total"]
    )
    assert len(_spec("active")["include_ids"]) == metrics["activeUsers"]


def test_spec_unknown_segment_falls_back_to_all():
    assert _spec("nonsense") == _spec("all")


# ---------------------------------------------------------------------------
# admin_segment_users resolver
# ---------------------------------------------------------------------------


def test_admin_segment_users_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception("Acceso denegado")

    monkeypatch.setattr(queries, "require_role", _deny)
    sources = AsyncMock()
    monkeypatch.setattr(queries.users_repo, "get_metrics_sources", sources)

    query = queries.UserQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(query.admin_segment_users(info=None, jwt="token"))
    sources.assert_not_awaited()


def _mock_user(uid, **over):
    base = dict(
        id=uid,
        name="Ana",
        email="ana@example.com",
        username="ana",
        phone=None,
        createdAt=None,
        lastSeenAt=None,
        authProvider="local",
        walletStatus="active",
        deliveredOrdersCount=0,
        scheduledDeletionAt=None,
        avatar=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _patch_sources(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    monkeypatch.setattr(
        queries.users_repo,
        "get_metrics_sources",
        AsyncMock(
            return_value={
                "total_users": 10,
                "new_users": 1,
                "courier_ids": {"c1"},
                "business_ids": {"b1"},
                "active_ids": {"c1"},
            }
        ),
    )


def test_admin_segment_users_flags_app_membership(monkeypatch):
    _patch_sources(monkeypatch)
    monkeypatch.setattr(
        queries.users_repo,
        "list_segment",
        AsyncMock(return_value=([_mock_user("c1"), _mock_user("z9")], 2)),
    )

    query = queries.UserQuery()
    result = asyncio.run(query.admin_segment_users(info=None, jwt="t"))

    courier_row, plain_row = result.rows
    assert (courier_row.isCourier, courier_row.isActive) == (True, True)
    assert (plain_row.isCourier, plain_row.isBusiness, plain_row.isActive) == (
        False,
        False,
        False,
    )
    assert result.totalCount == 2
    assert result.hasMore is False


def test_admin_segment_users_reports_has_more(monkeypatch):
    _patch_sources(monkeypatch)
    monkeypatch.setattr(
        queries.users_repo,
        "list_segment",
        AsyncMock(return_value=([_mock_user("a1")], 25)),
    )

    query = queries.UserQuery()
    result = asyncio.run(
        query.admin_segment_users(info=None, jwt="t", limit=1, offset=0)
    )
    assert result.hasMore is True


def test_admin_segment_users_clamps_limit_and_offset(monkeypatch):
    _patch_sources(monkeypatch)
    list_segment = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(queries.users_repo, "list_segment", list_segment)

    query = queries.UserQuery()
    asyncio.run(
        query.admin_segment_users(info=None, jwt="t", limit=9999, offset=-5)
    )

    kwargs = list_segment.await_args.kwargs
    assert kwargs["limit"] == 200
    assert kwargs["offset"] == 0
