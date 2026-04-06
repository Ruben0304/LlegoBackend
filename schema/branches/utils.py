"""Utility functions for Branch GraphQL types."""

from domain.models import Branch
from schema.branches.types import (
    BranchTipo,
    BranchVehicle,
    CoordinatesType,
    TransferAccountType,
)
from schema.wallet.types import WalletBalanceType
from utils.serialization import to_strawberry_dict

from .transfer_accounts import (
    build_pago_qr,
    normalize_card_number,
    normalize_confirm_phone,
    normalize_holder_name,
)


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
    # New crypto/digital payment fields â€” default to safe values if not in DB yet
    branch_dict.setdefault("acceptsQvapay", False)
    branch_dict.setdefault("acceptsZelle", False)
    branch_dict.setdefault("qvapayUsername", None)
    branch_dict.setdefault("zelleEmail", None)
    branch_dict.setdefault("pickupEnabled", False)
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
    legacy_phones = [to_strawberry_dict(p).get("phone") for p in (branch.phones or [])]
    transfer_accounts = []
    for idx, account in enumerate(branch.accounts or []):
        account_data = to_strawberry_dict(account)
        card_number = normalize_card_number(
            account_data.get("cardNumber"), strict=False
        ) or ""
        confirm_phone = normalize_confirm_phone(
            account_data.get("confirmPhone"), strict=False
        )

        if not confirm_phone and idx < len(legacy_phones):
            confirm_phone = normalize_confirm_phone(legacy_phones[idx], strict=False)

        # Keep API stable for legacy records where confirmPhone was not stored.
        confirm_phone = confirm_phone or ""

        transfer_accounts.append(
            TransferAccountType(
                cardNumber=card_number,
                confirmPhone=confirm_phone,
                cardHolderName=normalize_holder_name(
                    account_data.get("cardHolderName")
                ),
                pagoQr=(
                    build_pago_qr(card_number, confirm_phone)
                    if card_number and confirm_phone
                    else None
                ),
                isActive=bool(account_data.get("isActive", True)),
            )
        )
    branch_dict["accounts"] = transfer_accounts
    return branch_dict
