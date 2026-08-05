"""Unit tests for the branch delivery request concurrency fixes.

These test the *resolver logic* against mocked repositories, matching the
project's existing test convention (unittest.mock.AsyncMock / SimpleNamespace,
no live or mocked MongoDB — see tests/test_cash_kyc_integration.py). The
partial-unique-index and atomic find_one_and_update behavior these fixes rely
on can only be verified against a real MongoDB and are NOT covered here; that
requires a manual/staging check (see docs/plan-features session notes).
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import schema.orders.mutations as mutations
import schema.orders.queries as queries
from domain.orders import DeliveryRequestStatus
from schema.orders.inputs import RequestBranchLinkInput, RespondBranchLinkInput

USER_ID = "507f1f77bcf86cd799439099"
DELIVERY_PERSON_ID = "507f1f77bcf86cd799439011"
BRANCH_ID = "507f1f77bcf86cd799439012"
REQUEST_ID = "507f1f77bcf86cd799439013"


def _mock_branch(manager_ids=None, use_app_messaging=True):
    return SimpleNamespace(
        id=BRANCH_ID,
        managerIds=manager_ids or [USER_ID],
        useAppMessaging=use_app_messaging,
    )


def _mock_pending_request():
    return SimpleNamespace(
        id=REQUEST_ID,
        deliveryPersonId=DELIVERY_PERSON_ID,
        branchId=BRANCH_ID,
        status=DeliveryRequestStatus.PENDING,
    )


@pytest.fixture
def patch_auth(monkeypatch):
    monkeypatch.setattr(mutations, "require_auth", lambda jwt, info: USER_ID)
    monkeypatch.setattr(
        queries,
        "_get_or_create_delivery_person",
        AsyncMock(return_value=SimpleNamespace(id=DELIVERY_PERSON_ID)),
    )


def test_request_branch_link_duplicate_key_error_becomes_friendly_message(
    monkeypatch, patch_auth
):
    """A race lost between get_existing() and create() surfaces as the same
    friendly message the pre-race get_existing() check already raises,
    instead of a raw DuplicateKeyError bubbling up as a 500."""
    monkeypatch.setattr(
        mutations.branches_repo, "get_by_id", AsyncMock(return_value=_mock_branch())
    )
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "get_existing",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "create",
        AsyncMock(side_effect=DuplicateKeyError("dup")),
    )

    mutation = mutations.OrderMutation()
    with pytest.raises(Exception, match="Ya tienes una solicitud pendiente"):
        asyncio.run(
            mutation.request_branch_link(
                info=None,
                input=RequestBranchLinkInput(branchId=BRANCH_ID, message=None),
                jwt="token",
            )
        )


def test_respond_branch_link_request_lost_race_raises_already_responded(
    monkeypatch, patch_auth
):
    """update_status() returning None (its CAS filter matched nothing because
    someone else already responded) must surface as an error, not be treated
    as a successful response."""
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_pending_request()),
    )
    monkeypatch.setattr(
        mutations.branches_repo, "get_by_id", AsyncMock(return_value=_mock_branch())
    )
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "update_status",
        AsyncMock(return_value=None),
    )
    add_linked_branch = AsyncMock()
    monkeypatch.setattr(
        mutations.delivery_persons_repo, "add_linked_branch", add_linked_branch
    )

    mutation = mutations.OrderMutation()
    with pytest.raises(Exception, match="ya fue respondida"):
        asyncio.run(
            mutation.respond_branch_link_request(
                info=None,
                input=RespondBranchLinkInput(requestId=REQUEST_ID, accept=True),
                jwt="token",
            )
        )

    add_linked_branch.assert_not_awaited()


def test_respond_branch_link_request_accept_still_links_on_success(
    monkeypatch, patch_auth
):
    """Regression guard: the happy path (no race) still links the delivery
    person when the update actually wins and the branch uses app messaging."""
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_pending_request()),
    )
    monkeypatch.setattr(
        mutations.branches_repo, "get_by_id", AsyncMock(return_value=_mock_branch())
    )
    accepted = SimpleNamespace(
        id=REQUEST_ID,
        deliveryPersonId=DELIVERY_PERSON_ID,
        branchId=BRANCH_ID,
        status=DeliveryRequestStatus.ACCEPTED,
    )
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "update_status",
        AsyncMock(return_value=accepted),
    )
    add_linked_branch = AsyncMock()
    monkeypatch.setattr(
        mutations.delivery_persons_repo, "add_linked_branch", add_linked_branch
    )
    monkeypatch.setattr(
        mutations, "branch_delivery_request_to_type", lambda req: req
    )

    mutation = mutations.OrderMutation()
    result = asyncio.run(
        mutation.respond_branch_link_request(
            info=None,
            input=RespondBranchLinkInput(requestId=REQUEST_ID, accept=True),
            jwt="token",
        )
    )

    assert result.status == DeliveryRequestStatus.ACCEPTED
    add_linked_branch.assert_awaited_once_with(DELIVERY_PERSON_ID, BRANCH_ID)


def test_cancel_branch_link_request_lost_race_raises_already_responded(
    monkeypatch, patch_auth
):
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "get_by_id",
        AsyncMock(return_value=_mock_pending_request()),
    )
    monkeypatch.setattr(
        mutations.branch_delivery_requests_repo,
        "update_status",
        AsyncMock(return_value=None),
    )

    mutation = mutations.OrderMutation()
    with pytest.raises(Exception, match="ya fue respondida"):
        asyncio.run(
            mutation.cancel_branch_link_request(
                info=None, requestId=REQUEST_ID, jwt="token"
            )
        )
