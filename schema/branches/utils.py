"""Utility functions for Branch GraphQL types."""

from models import Branch
from schema.branches.types import (
    BranchTipo,
    BranchVehicle,
    CoordinatesType,
    QrPaymentType,
    TransferAccountType,
    TransferPhoneType,
)
from schema.wallet.types import WalletBalanceType


def branch_to_dict(branch: Branch) -> dict:
    """Convert Branch model to dict suitable for BranchType instantiation."""
    branch_dict = branch.model_dump(
        exclude={
            "wallet",
            "walletStatus",
            "coordinates",
            "tipos",
            "vehicles",
            "accounts",
            "qrPayments",
            "phones",
        }
    )
    branch_dict["coordinates"] = CoordinatesType(**branch.coordinates.model_dump())
    branch_dict["tipos"] = [BranchTipo(t) for t in (branch.tipos or [])]
    branch_dict["vehicles"] = [BranchVehicle(v) for v in (branch.vehicles or [])]
    branch_dict["wallet"] = WalletBalanceType(
        local=branch.wallet.get("local", 0.0), usd=branch.wallet.get("usd", 0.0)
    )
    branch_dict["walletStatus"] = branch.walletStatus
    branch_dict["accounts"] = [
        TransferAccountType(**a.model_dump()) for a in (branch.accounts or [])
    ]
    branch_dict["qrPayments"] = [
        QrPaymentType(**q.model_dump()) for q in (branch.qrPayments or [])
    ]
    branch_dict["phones"] = [
        TransferPhoneType(**p.model_dump()) for p in (branch.phones or [])
    ]
    return branch_dict
