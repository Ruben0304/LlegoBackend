"""GraphQL query resolvers for Wallet."""
import strawberry
from typing import List, Optional
from strawberry.types import Info
from decimal import Decimal

from .types import WalletStatusType, WalletBalanceType, WalletTransactionType
from .utils import to_object_id
from services.wallet_service import wallet_service
from utils.graphql_auth import require_auth


@strawberry.type
class WalletQuery:
    @strawberry.field(description="Obtener balance de wallet del usuario actual")
    async def my_wallet(self, info: Info, jwt: str) -> WalletStatusType:
        """Get current user's wallet balance and status."""
        user_id = require_auth(jwt, info)
        
        balance = await wallet_service.get_balance(user_id, "user")
        
        # Get wallet status from user document
        from clients.mongodb_client import get_database
        db = get_database()
        user = await db.users.find_one({"_id": to_object_id(user_id)})
        wallet_status = user.get("walletStatus", "active") if user else "active"
        
        return WalletStatusType(
            balance=WalletBalanceType(
                local=balance.get("local", 0.0),
                usd=balance.get("usd", 0.0)
            ),
            status=wallet_status
        )

    @strawberry.field(description="Obtener historial de transacciones del usuario actual")
    async def my_wallet_transactions(
        self,
        info: Info,
        jwt: str,
        limit: int = 50,
        skip: int = 0,
        currency: Optional[str] = None
    ) -> List[WalletTransactionType]:
        """Get current user's wallet transaction history."""
        user_id = require_auth(jwt, info)
        
        transactions = await wallet_service.get_transaction_history(
            owner_id=user_id,
            owner_type="user",
            limit=limit,
            skip=skip,
            currency=currency
        )
        
        return [
            WalletTransactionType(
                id=tx["_id"],
                from_owner_id=tx.get("fromOwnerId"),
                from_owner_type=tx.get("fromOwnerType"),
                to_owner_id=tx.get("toOwnerId"),
                to_owner_type=tx.get("toOwnerType"),
                amount=tx["amount"],
                currency=tx["currency"],
                type=tx["type"],
                status=tx["status"],
                description=tx.get("description"),
                created_at=tx["createdAt"],
                completed_at=tx.get("completedAt")
            )
            for tx in transactions
        ]

    @strawberry.field(description="Obtener balance de wallet de una sucursal")
    async def branch_wallet(
        self,
        info: Info,
        branch_id: str,
        jwt: str
    ) -> WalletStatusType:
        """Get branch wallet balance. Only branch managers or business owner can access."""
        user_id = require_auth(jwt, info)
        
        # Verify user is manager of branch or owner of business
        from clients.mongodb_client import get_database
        db = get_database()
        branch = await db.branches.find_one({"_id": to_object_id(branch_id)})
        
        if not branch:
            raise Exception("Sucursal no encontrada")
        
        # Check if user is manager of this branch
        is_manager = user_id in branch.get("managerIds", [])
        
        # Check if user is owner of the business
        business = await db.businesses.find_one({"_id": to_object_id(branch["businessId"])})
        is_owner = business and business["ownerId"] == user_id
        
        if not is_manager and not is_owner:
            raise Exception("No autorizado: solo los managers de la sucursal o el dueño del negocio pueden ver la wallet")
        
        balance = await wallet_service.get_balance(branch_id, "branch")
        wallet_status = branch.get("walletStatus", "active")
        
        return WalletStatusType(
            balance=WalletBalanceType(
                local=balance.get("local", 0.0),
                usd=balance.get("usd", 0.0)
            ),
            status=wallet_status
        )

    @strawberry.field(description="Obtener historial de transacciones de una sucursal")
    async def branch_wallet_transactions(
        self,
        info: Info,
        branch_id: str,
        jwt: str,
        limit: int = 50,
        skip: int = 0,
        currency: Optional[str] = None
    ) -> List[WalletTransactionType]:
        """Get branch wallet transaction history. Only branch managers or business owner can access."""
        user_id = require_auth(jwt, info)
        
        # Verify user is manager of branch or owner of business
        from clients.mongodb_client import get_database
        db = get_database()
        branch = await db.branches.find_one({"_id": to_object_id(branch_id)})
        
        if not branch:
            raise Exception("Sucursal no encontrada")
        
        # Check if user is manager of this branch
        is_manager = user_id in branch.get("managerIds", [])
        
        # Check if user is owner of the business
        business = await db.businesses.find_one({"_id": to_object_id(branch["businessId"])})
        is_owner = business and business["ownerId"] == user_id
        
        if not is_manager and not is_owner:
            raise Exception("No autorizado: solo los managers de la sucursal o el dueño del negocio pueden ver las transacciones")
        
        transactions = await wallet_service.get_transaction_history(
            owner_id=branch_id,
            owner_type="branch",
            limit=limit,
            skip=skip,
            currency=currency
        )
        
        return [
            WalletTransactionType(
                id=tx["_id"],
                from_owner_id=tx.get("fromOwnerId"),
                from_owner_type=tx.get("fromOwnerType"),
                to_owner_id=tx.get("toOwnerId"),
                to_owner_type=tx.get("toOwnerType"),
                amount=tx["amount"],
                currency=tx["currency"],
                type=tx["type"],
                status=tx["status"],
                description=tx.get("description"),
                created_at=tx["createdAt"],
                completed_at=tx.get("completedAt")
            )
            for tx in transactions
        ]
