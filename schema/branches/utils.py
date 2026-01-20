"""Utility functions for Branch GraphQL types."""
from models import Branch
from schema.wallet.types import WalletBalanceType


def branch_to_dict(branch: Branch) -> dict:
    """Convert Branch model to dict suitable for BranchType instantiation."""
    branch_dict = branch.model_dump(exclude={'wallet', 'walletStatus'})
    branch_dict['wallet'] = WalletBalanceType(
        local=branch.wallet.get('local', 0.0),
        usd=branch.wallet.get('usd', 0.0)
    )
    branch_dict['walletStatus'] = branch.walletStatus
    return branch_dict
