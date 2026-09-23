"""Unit tests for the admin orders/tracking/couriers-presence queries.

Same convention as tests/test_admin_kyc_queries.py: resolver logic against
mocked repositories/services, no live or mocked MongoDB/Redis.
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

import schema.orders.queries as queries
from services.orders_service import order_service

ORDER_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"
BUSINESS_ID = "507f1f77bcf86cd799439013"
CUSTOMER_ID = "507f1f77bcf86cd799439014"
OTHER_USER_ID = "507f1f77bcf86cd799439099"


def _mock_order(**overrides):
    defaults = dict(
        id=ORDER_ID,
        orderNumber="ORD-1",
        status="on_the_way",
        customerId=CUSTOMER_ID,
        branchId=BRANCH_ID,
        businessId=BUSINESS_ID,
        deliveryPersonId=None,
        deliveryMode="app",
        deliveryAddress=SimpleNamespace(
            coordinates=SimpleNamespace(coordinates=[-82.35, 23.13])
        ),
        pickupAddress=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mock_branch():
    return SimpleNamespace(
        id=BRANCH_ID,
        managerIds=[],
        coordinates=SimpleNamespace(coordinates=[-82.36, 23.12]),
    )


def _mock_business(owner_id="not-the-caller"):
    return SimpleNamespace(id=BUSINESS_ID, ownerId=owner_id)


# ---------------------------------------------------------------------------
# admin_orders
# ---------------------------------------------------------------------------


def test_admin_orders_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception(f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}")

    monkeypatch.setattr(queries, "require_role", _deny)
    list_filtered = AsyncMock()
    monkeypatch.setattr(queries.orders_repo, "list_filtered", list_filtered)

    query = queries.OrderQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(query.admin_orders(info=None, jwt="token"))
    list_filtered.assert_not_awaited()


def test_admin_orders_assembles_connection_from_repo(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    orders = [_mock_order(), _mock_order(id="507f1f77bcf86cd799439098")]
    monkeypatch.setattr(
        queries.orders_repo, "list_filtered", AsyncMock(return_value=(orders, 2))
    )
    monkeypatch.setattr(queries, "order_to_type", lambda o: o)

    query = queries.OrderQuery()
    result = asyncio.run(
        query.admin_orders(info=None, jwt="token", statusIn=["on_the_way"])
    )

    assert result.totalCount == 2
    assert result.hasMore is False
    assert len(result.orders) == 2


# ---------------------------------------------------------------------------
# admin_order_tracking
# ---------------------------------------------------------------------------


def test_admin_order_tracking_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception("Acceso denegado")

    monkeypatch.setattr(queries, "require_role", _deny)
    tracking = AsyncMock()
    monkeypatch.setattr(queries.order_service, "get_order_tracking", tracking)

    query = queries.OrderQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            query.admin_order_tracking(info=None, orderId=ORDER_ID, jwt="token")
        )
    tracking.assert_not_awaited()


def test_admin_order_tracking_passes_bypass_flag(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    tracking = AsyncMock(
        return_value={
            "order": _mock_order(),
            "storeLocation": {"longitude": -82.36, "latitude": 23.12},
            "deliveryLocation": {"longitude": -82.35, "latitude": 23.13},
            "deliveryPersonLocation": None,
        }
    )
    monkeypatch.setattr(queries.order_service, "get_order_tracking", tracking)
    monkeypatch.setattr(queries, "order_to_type", lambda o: o)

    query = queries.OrderQuery()
    result = asyncio.run(
        query.admin_order_tracking(info=None, orderId=ORDER_ID, jwt="token")
    )

    tracking.assert_awaited_once_with(ORDER_ID, user_id="", bypass_authorization=True)
    assert result.deliveryPersonLocation is None


# ---------------------------------------------------------------------------
# get_order_tracking(bypass_authorization=...) — regression guard on the flag itself
# ---------------------------------------------------------------------------


def test_get_order_tracking_bypass_authorization_skips_ownership_check(monkeypatch):
    monkeypatch.setattr(
        order_service.orders_repo, "get_by_id", AsyncMock(return_value=_mock_order())
    )
    monkeypatch.setattr(
        "services.orders_service.branches_repo.get_by_id",
        AsyncMock(return_value=_mock_branch()),
    )
    monkeypatch.setattr(
        "services.orders_service.businesses_repo.get_by_id",
        AsyncMock(return_value=_mock_business(owner_id="not-the-caller")),
    )

    result = asyncio.run(
        order_service.get_order_tracking(
            ORDER_ID, user_id=OTHER_USER_ID, bypass_authorization=True
        )
    )
    assert result["order"].id == ORDER_ID


def test_get_order_tracking_without_bypass_still_enforces_ownership(monkeypatch):
    monkeypatch.setattr(
        order_service.orders_repo, "get_by_id", AsyncMock(return_value=_mock_order())
    )
    monkeypatch.setattr(
        "services.orders_service.branches_repo.get_by_id",
        AsyncMock(return_value=_mock_branch()),
    )
    monkeypatch.setattr(
        "services.orders_service.businesses_repo.get_by_id",
        AsyncMock(return_value=_mock_business(owner_id="not-the-caller")),
    )

    with pytest.raises(ValueError, match="No autorizado"):
        asyncio.run(
            order_service.get_order_tracking(
                ORDER_ID, user_id=OTHER_USER_ID, bypass_authorization=False
            )
        )


# ---------------------------------------------------------------------------
# admin_couriers_presence
# ---------------------------------------------------------------------------


def test_admin_couriers_presence_denies_non_admin_role(monkeypatch):
    def _deny(jwt, info, allowed_roles):
        raise Exception("Acceso denegado")

    monkeypatch.setattr(queries, "require_role", _deny)
    snapshot = AsyncMock()
    monkeypatch.setattr(queries, "get_courier_presence_snapshot", snapshot)

    query = queries.OrderQuery()
    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(query.admin_couriers_presence(info=None, jwt="token"))
    snapshot.assert_not_awaited()


def test_admin_couriers_presence_returns_snapshot(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda jwt, info, roles: "admin-id")
    presence = [SimpleNamespace(deliveryPersonId="dp-1", isOnline=True)]
    monkeypatch.setattr(
        queries, "get_courier_presence_snapshot", AsyncMock(return_value=presence)
    )

    query = queries.OrderQuery()
    result = asyncio.run(query.admin_couriers_presence(info=None, jwt="token"))

    assert result == presence
