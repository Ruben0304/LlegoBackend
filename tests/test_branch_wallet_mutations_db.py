"""branchTransferMoney y branchWithdrawMoney ya no lanzan NameError.

Usaban `db.wallet_transactions` sin definir `db` (context.md §12.1): el dinero
se movia y el cliente recibia un error. Solo se comprueba el arreglo minimo; la
wallet no es feature del MVP.
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_BUCKET_NAME", "test")

import pytest

import schema.wallet.mutations as wallet_mutations
from schema.wallet.inputs import TransferInput, WithdrawInput

OWNER_ID = "507f1f77bcf86cd799439014"
BRANCH_ID = "507f1f77bcf86cd799439012"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(wallet_mutations, "require_auth", lambda jwt, info: OWNER_ID)
    monkeypatch.setattr(
        wallet_mutations.branches_repo,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(managerIds=[], businessId="biz-1")),
    )
    monkeypatch.setattr(
        wallet_mutations.businesses_repo,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(ownerId=OWNER_ID)),
    )
    monkeypatch.setattr(
        wallet_mutations.wallet_service, "transfer", AsyncMock(return_value={"transaction_id": "tx-1"})
    )
    monkeypatch.setattr(
        wallet_mutations.wallet_service, "withdraw", AsyncMock(return_value={"transaction_id": "tx-1"})
    )
    db = MagicMock()
    db.wallet_transactions.find_one = AsyncMock(return_value={
        "_id": "tx-1", "amount": 5.0, "currency": "usd", "type": "transfer",
        "status": "completed", "createdAt": datetime(2026, 10, 1),
    })
    with patch("clients.mongodb_client.get_database", return_value=db):
        yield db


def test_branch_transfer_money_returns_transaction(env):
    tx = asyncio.run(wallet_mutations.WalletMutation().branch_transfer_money(
        info=None, branch_id=BRANCH_ID, jwt="t",
        input=TransferInput(to_owner_id="u-2", to_owner_type="user", amount=5.0, currency="usd"),
    ))

    assert tx.id == "tx-1"
    env.wallet_transactions.find_one.assert_awaited_once_with({"_id": "tx-1"})


def test_branch_withdraw_money_returns_transaction(env):
    tx = asyncio.run(wallet_mutations.WalletMutation().branch_withdraw_money(
        info=None, branch_id=BRANCH_ID, jwt="t",
        input=WithdrawInput(amount=5.0, currency="usd", destination="cuenta"),
    ))

    assert tx.id == "tx-1"
    env.wallet_transactions.find_one.assert_awaited_once_with({"_id": "tx-1"})
