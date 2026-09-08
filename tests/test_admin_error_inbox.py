"""Unit tests for the admin error inbox (GraphQL) and the REST auth guard.

Same convention as tests/test_admin_user_metrics.py: resolvers against mocked
repositories, no live MongoDB.
"""

import asyncio
import os
from datetime import datetime
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
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

import schema.error_logs.mutations as mutations
import schema.error_logs.queries as queries
from schema.error_logs.types import buckets_to_types, error_log_to_type

ERROR_ID = "507f1f77bcf86cd799439011"
ADMIN_ID = "507f1f77bcf86cd799439099"


def _mock_analysis(**over):
    base = dict(
        resumen="Falla al serializar la orden",
        tipo_error="TypeError",
        causa_probable="Campo nuevo no declarado en el tipo GraphQL",
        soluciones=["Declarar el campo", "Excluirlo del dict"],
        severidad=SimpleNamespace(value="critica"),
        requiere_accion_inmediata=True,
        archivo="schema/orders/types.py",
        linea=42,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _mock_log(**over):
    base = dict(
        id=ERROR_ID,
        error_type="TypeError",
        error_message="unexpected keyword argument",
        stack_trace="Traceback...",
        endpoint="/graphql",
        http_method="POST",
        client_ip="1.2.3.4",
        user_agent="LlegoiOS/1.5",
        user_id=None,
        source=SimpleNamespace(value="backend"),
        app_version=None,
        device_info=None,
        screen=None,
        action=None,
        extra_data=None,
        gemini_analysis=None,
        resolved=False,
        resolved_at=None,
        resolved_by=None,
        occurrence_count=3,
        last_occurrence_at=datetime(2026, 9, 1),
        created_at=datetime(2026, 8, 30),
    )
    base.update(over)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_error_log_maps_snake_case_model_to_camel_case_type():
    row = error_log_to_type(_mock_log())
    assert row.id == ERROR_ID
    assert row.errorType == "TypeError"
    assert row.occurrenceCount == 3
    assert row.source == "backend"
    assert row.geminiAnalysis is None


def test_error_log_maps_the_ai_analysis():
    row = error_log_to_type(_mock_log(gemini_analysis=_mock_analysis()))
    analysis = row.geminiAnalysis
    assert analysis.severidad == "critica"
    assert analysis.requiereAccionInmediata is True
    assert analysis.archivo == "schema/orders/types.py"
    assert analysis.linea == 42
    assert len(analysis.soluciones) == 2


def test_error_log_serialises_extra_data_as_json():
    row = error_log_to_type(_mock_log(extra_data={"orderId": "abc"}))
    assert row.extraDataJson == '{"orderId": "abc"}'


def test_buckets_are_sorted_by_count_descending():
    result = buckets_to_types({"baja": 2, "critica": 9, "media": 5})
    assert [b.key for b in result] == ["critica", "media", "baja"]
    assert [b.count for b in result] == [9, 5, 2]


def test_buckets_handle_empty_input():
    assert buckets_to_types({}) == []
    assert buckets_to_types(None) == []


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _deny(jwt, info, allowed_roles):
    raise Exception("Acceso denegado")


def test_admin_error_logs_denies_non_admin_role(monkeypatch):
    monkeypatch.setattr(queries, "require_role", _deny)
    paginated = AsyncMock()
    monkeypatch.setattr(queries.error_log_repo, "get_paginated", paginated)

    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(queries.ErrorLogQuery().admin_error_logs(info=None, jwt="t"))
    paginated.assert_not_awaited()


def test_admin_error_stats_denies_non_admin_role(monkeypatch):
    monkeypatch.setattr(queries, "require_role", _deny)
    stats = AsyncMock()
    monkeypatch.setattr(queries.error_log_repo, "get_stats", stats)

    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(queries.ErrorLogQuery().admin_error_stats(info=None, jwt="t"))
    stats.assert_not_awaited()


def test_admin_error_logs_reports_has_more_across_pages(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda j, i, r: ADMIN_ID)
    monkeypatch.setattr(
        queries.error_log_repo,
        "get_paginated",
        AsyncMock(return_value=([_mock_log()] * 20, 45)),
    )

    result = asyncio.run(
        queries.ErrorLogQuery().admin_error_logs(
            info=None, jwt="t", page=1, pageSize=20
        )
    )
    assert result.totalCount == 45
    assert result.hasMore is True


def test_admin_error_logs_last_page_has_no_more(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda j, i, r: ADMIN_ID)
    monkeypatch.setattr(
        queries.error_log_repo,
        "get_paginated",
        AsyncMock(return_value=([_mock_log()] * 5, 45)),
    )

    result = asyncio.run(
        queries.ErrorLogQuery().admin_error_logs(
            info=None, jwt="t", page=3, pageSize=20
        )
    )
    assert result.hasMore is False


def test_admin_error_logs_clamps_page_and_size(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda j, i, r: ADMIN_ID)
    paginated = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(queries.error_log_repo, "get_paginated", paginated)

    asyncio.run(
        queries.ErrorLogQuery().admin_error_logs(
            info=None, jwt="t", page=0, pageSize=9999
        )
    )
    kwargs = paginated.await_args.kwargs
    assert kwargs["page"] == 1
    assert kwargs["page_size"] == 100


def test_admin_error_stats_maps_facet_result(monkeypatch):
    monkeypatch.setattr(queries, "require_role", lambda j, i, r: ADMIN_ID)
    monkeypatch.setattr(
        queries.error_log_repo,
        "get_stats",
        AsyncMock(
            return_value={
                "total_errors": 10,
                "resolved_errors": 4,
                "pending_errors": 6,
                "by_severity": {"critica": 2, "baja": 8},
                "by_source": {"backend": 10},
                "by_type": {"TypeError": 7},
                "critical_unresolved": 2,
                "period_days": 7,
            }
        ),
    )

    result = asyncio.run(
        queries.ErrorLogQuery().admin_error_stats(info=None, jwt="t", days=7)
    )
    assert (result.totalErrors, result.pendingErrors) == (10, 6)
    assert result.criticalUnresolved == 2
    assert result.bySeverity[0].key == "baja"  # sorted by count desc


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def test_resolve_denies_non_admin_role(monkeypatch):
    monkeypatch.setattr(mutations, "require_role", _deny)
    mark = AsyncMock()
    monkeypatch.setattr(mutations.error_log_repo, "mark_resolved", mark)

    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            mutations.ErrorLogMutation().admin_resolve_error(
                info=None, errorId=ERROR_ID, jwt="t"
            )
        )
    mark.assert_not_awaited()


def test_resolve_records_which_admin_did_it(monkeypatch):
    """resolved_by must be the acting admin, not left blank."""
    monkeypatch.setattr(mutations, "require_role", lambda j, i, r: ADMIN_ID)
    mark = AsyncMock(return_value=True)
    monkeypatch.setattr(mutations.error_log_repo, "mark_resolved", mark)

    ok = asyncio.run(
        mutations.ErrorLogMutation().admin_resolve_error(
            info=None, errorId=ERROR_ID, jwt="t"
        )
    )
    assert ok is True
    mark.assert_awaited_once_with(ERROR_ID, resolved_by=ADMIN_ID)


def test_unresolve_denies_non_admin_role(monkeypatch):
    monkeypatch.setattr(mutations, "require_role", _deny)
    mark = AsyncMock()
    monkeypatch.setattr(mutations.error_log_repo, "mark_unresolved", mark)

    with pytest.raises(Exception, match="Acceso denegado"):
        asyncio.run(
            mutations.ErrorLogMutation().admin_unresolve_error(
                info=None, errorId=ERROR_ID, jwt="t"
            )
        )
    mark.assert_not_awaited()


# ---------------------------------------------------------------------------
# REST guard — these endpoints leaked stack traces and could send pushes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rest_client():
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_key(monkeypatch):
    """Pin the configured admin key for the duration of a test.

    `settings` is a module-level singleton built at import time, so whether
    ADMIN_API_KEY was in the environment depends on which test file imported
    core.config first. require_admin_api_key reads the attribute at call time,
    so patching it here makes these tests independent of import order —
    otherwise they pass alone and fail in the full suite (503 "key not
    configured" instead of 401).
    """
    from core.config import settings

    monkeypatch.setattr(settings, "admin_api_key", "test-admin-key")
    return "test-admin-key"


ADMIN_ROUTES = [
    ("GET", "/api/error-logs/"),
    ("GET", "/api/error-logs/stats"),
    ("GET", f"/api/error-logs/{ERROR_ID}"),
    ("DELETE", "/api/error-logs/cleanup"),
    ("POST", "/api/error-logs/test-push/clientes"),
    ("POST", "/api/error-logs/test-push/negocios"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_rest_endpoints_reject_missing_token(
    rest_client, admin_key, method, path
):
    assert rest_client.request(method, path).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_rest_endpoints_reject_wrong_token(
    rest_client, admin_key, method, path
):
    response = rest_client.request(
        method, path, headers={"Authorization": "Bearer wrong-key"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_rest_endpoints_accept_the_configured_key(
    rest_client, admin_key, method, path
):
    """With the right key the guard lets the request through — anything past
    auth (including a 500 from the DB not being connected in tests) proves the
    endpoint isn't simply refusing everyone."""
    response = rest_client.request(
        method, path, headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert response.status_code not in (401, 403)


def test_admin_rest_endpoints_fail_closed_without_a_configured_key(
    rest_client, monkeypatch
):
    """No key configured must lock the endpoints, never open them."""
    from core.config import settings

    monkeypatch.setattr(settings, "admin_api_key", "")
    response = rest_client.get(
        "/api/error-logs/stats", headers={"Authorization": "Bearer anything"}
    )
    assert response.status_code == 503


def test_mobile_report_intake_stays_open(rest_client):
    """The apps have no admin key — locking this would kill crash reporting."""
    status = rest_client.post("/api/error-logs/mobile-report", json={}).status_code
    assert status != 401
