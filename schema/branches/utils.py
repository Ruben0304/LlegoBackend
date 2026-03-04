"""Utility functions for Branch GraphQL types."""

from domain.models import Branch
from schema.branches.types import (
    BranchTipo,
    BranchVehicle,
    CoordinatesType,
    QrPaymentType,
    TransferAccountType,
    TransferPhoneType,
)
from schema.wallet.types import WalletBalanceType
from utils.serialization import to_strawberry_dict


def branch_to_dict(branch: Branch) -> dict:
    """Convert Branch model to dict suitable for BranchType instantiation."""
    branch_dict = to_strawberry_dict(
        branch,
        exclude={
            "wallet",
            "walletStatus",
            "coordinates",
            "tipos",
            "vehicles",
            "accounts",
            "qrPayments",
            "phones",
        },
    )
    # Keep a stable string value for status to avoid null decoding failures in clients.
    if not branch_dict.get("status"):
        branch_dict["status"] = "active" if getattr(branch, "isActive", False) else "inactive"

    coordinates_data = to_strawberry_dict(branch.coordinates)
    branch_dict["coordinates"] = CoordinatesType(
        type=coordinates_data.get("type", "Point"),
        coordinates=coordinates_data.get("coordinates", []),
    )
    branch_dict["tipos"] = [BranchTipo(t) for t in (branch.tipos or [])]
    branch_dict["vehicles"] = [BranchVehicle(v) for v in (branch.vehicles or [])]
    branch_dict["wallet"] = WalletBalanceType(
        local=branch.wallet.get("local", 0.0), usd=branch.wallet.get("usd", 0.0)
    )
    branch_dict["walletStatus"] = branch.walletStatus
    branch_dict["accounts"] = [
        TransferAccountType(**to_strawberry_dict(a)) for a in (branch.accounts or [])
    ]
    branch_dict["qrPayments"] = [
        QrPaymentType(**to_strawberry_dict(q)) for q in (branch.qrPayments or [])
    ]
    branch_dict["phones"] = [
        TransferPhoneType(**to_strawberry_dict(p)) for p in (branch.phones or [])
    ]
    return branch_dict
