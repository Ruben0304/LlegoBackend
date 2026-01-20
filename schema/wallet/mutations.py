"""GraphQL mutations for Wallet operations."""
import strawberry
from typing import Optional
from strawberry.types import Info
from decimal import Decimal

from .types import WalletTransactionType
from .inputs import TransferInput, DepositInput, WithdrawInput
from .utils import to_object_id
from services.wallet_service import wallet_service
from utils.graphql_auth import require_auth


@strawberry.type
class WalletMutation:
    @strawberry.mutation(description="Transferir dinero a otro usuario o sucursal")
    async def transfer_money(
        self,
        info: Info,
        input: TransferInput,
        jwt: str
    ) -> WalletTransactionType:
        """Transfer money from current user to another user or branch."""
        user_id = require_auth(jwt, info)
        
        if input.amount <= 0:
            raise Exception("El monto debe ser mayor a 0")
        
        if input.currency not in ["local", "usd"]:
            raise Exception("Moneda inválida. Debe ser 'local' o 'usd'")
        
        if input.to_owner_type not in ["user", "branch"]:
            raise Exception("Tipo de destinatario inválido. Debe ser 'user' o 'branch'")
        
        result = await wallet_service.transfer(
            from_owner_id=user_id,
            from_owner_type="user",
            to_owner_id=input.to_owner_id,
            to_owner_type=input.to_owner_type,
            amount=Decimal(str(input.amount)),
            currency=input.currency,
            description=input.description
        )
        
        # Get transaction details
        from clients.mongodb_client import get_database
        db = get_database()
        transaction = await db.wallet_transactions.find_one({"_id": result["transaction_id"]})
        
        return WalletTransactionType(
            id=transaction["_id"],
            from_owner_id=transaction.get("fromOwnerId"),
            from_owner_type=transaction.get("fromOwnerType"),
            to_owner_id=transaction.get("toOwnerId"),
            to_owner_type=transaction.get("toOwnerType"),
            amount=transaction["amount"],
            currency=transaction["currency"],
            type=transaction["type"],
            status=transaction["status"],
            description=transaction.get("description"),
            created_at=transaction["createdAt"],
            completed_at=transaction.get("completedAt")
        )

    @strawberry.mutation(description="Depositar dinero en la wallet")
    async def deposit_money(
        self,
        info: Info,
        input: DepositInput,
        jwt: str
    ) -> WalletTransactionType:
        """Deposit money into current user's wallet."""
        user_id = require_auth(jwt, info)
        
        if input.amount <= 0:
            raise Exception("El monto debe ser mayor a 0")
        
        if input.currency not in ["local", "usd"]:
            raise Exception("Moneda inválida. Debe ser 'local' o 'usd'")
        
        result = await wallet_service.deposit(
            owner_id=user_id,
            owner_type="user",
            amount=Decimal(str(input.amount)),
            currency=input.currency,
            source=input.source,
            description=input.description
        )
        
        # Get transaction details
        from clients.mongodb_client import get_database
        db = get_database()
        transaction = await db.wallet_transactions.find_one({"_id": result["transaction_id"]})
        
        return WalletTransactionType(
            id=transaction["_id"],
            from_owner_id=transaction.get("fromOwnerId"),
            from_owner_type=transaction.get("fromOwnerType"),
            to_owner_id=transaction.get("toOwnerId"),
            to_owner_type=transaction.get("toOwnerType"),
            amount=transaction["amount"],
            currency=transaction["currency"],
            type=transaction["type"],
            status=transaction["status"],
            description=transaction.get("description"),
            created_at=transaction["createdAt"],
            completed_at=transaction.get("completedAt")
        )

    @strawberry.mutation(description="Retirar dinero de la wallet")
    async def withdraw_money(
        self,
        info: Info,
        input: WithdrawInput,
        jwt: str
    ) -> WalletTransactionType:
        """Withdraw money from current user's wallet."""
        user_id = require_auth(jwt, info)
        
        if input.amount <= 0:
            raise Exception("El monto debe ser mayor a 0")
        
        if input.currency not in ["local", "usd"]:
            raise Exception("Moneda inválida. Debe ser 'local' o 'usd'")
        
        result = await wallet_service.withdraw(
            owner_id=user_id,
            owner_type="user",
            amount=Decimal(str(input.amount)),
            currency=input.currency,
            destination=input.destination,
            description=input.description
        )
        
        # Get transaction details
        from clients.mongodb_client import get_database
        db = get_database()
        transaction = await db.wallet_transactions.find_one({"_id": result["transaction_id"]})
        
        return WalletTransactionType(
            id=transaction["_id"],
            from_owner_id=transaction.get("fromOwnerId"),
            from_owner_type=transaction.get("fromOwnerType"),
            to_owner_id=transaction.get("toOwnerId"),
            to_owner_type=transaction.get("toOwnerType"),
            amount=transaction["amount"],
            currency=transaction["currency"],
            type=transaction["type"],
            status=transaction["status"],
            description=transaction.get("description"),
            created_at=transaction["createdAt"],
            completed_at=transaction.get("completedAt")
        )

    @strawberry.mutation(description="Transferir dinero desde wallet de sucursal")
    async def branch_transfer_money(
        self,
        info: Info,
        branch_id: str,
        input: TransferInput,
        jwt: str
    ) -> WalletTransactionType:
        """Transfer money from branch wallet. Only branch managers or business owner can do this."""
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
            raise Exception("No autorizado: solo los managers de la sucursal o el dueño del negocio pueden transferir desde la wallet")
        
        if input.amount <= 0:
            raise Exception("El monto debe ser mayor a 0")
        
        if input.currency not in ["local", "usd"]:
            raise Exception("Moneda inválida. Debe ser 'local' o 'usd'")
        
        if input.to_owner_type not in ["user", "branch"]:
            raise Exception("Tipo de destinatario inválido. Debe ser 'user' o 'branch'")
        
        result = await wallet_service.transfer(
            from_owner_id=branch_id,
            from_owner_type="branch",
            to_owner_id=input.to_owner_id,
            to_owner_type=input.to_owner_type,
            amount=Decimal(str(input.amount)),
            currency=input.currency,
            description=input.description
        )
        
        # Get transaction details
        transaction = await db.wallet_transactions.find_one({"_id": result["transaction_id"]})
        
        return WalletTransactionType(
            id=transaction["_id"],
            from_owner_id=transaction.get("fromOwnerId"),
            from_owner_type=transaction.get("fromOwnerType"),
            to_owner_id=transaction.get("toOwnerId"),
            to_owner_type=transaction.get("toOwnerType"),
            amount=transaction["amount"],
            currency=transaction["currency"],
            type=transaction["type"],
            status=transaction["status"],
            description=transaction.get("description"),
            created_at=transaction["createdAt"],
            completed_at=transaction.get("completedAt")
        )

    @strawberry.mutation(description="Retirar dinero de wallet de sucursal")
    async def branch_withdraw_money(
        self,
        info: Info,
        branch_id: str,
        input: WithdrawInput,
        jwt: str
    ) -> WalletTransactionType:
        """Withdraw money from branch wallet. Only branch managers or business owner can do this."""
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
            raise Exception("No autorizado: solo los managers de la sucursal o el dueño del negocio pueden retirar de la wallet")
        
        if input.amount <= 0:
            raise Exception("El monto debe ser mayor a 0")
        
        if input.currency not in ["local", "usd"]:
            raise Exception("Moneda inválida. Debe ser 'local' o 'usd'")
        
        result = await wallet_service.withdraw(
            owner_id=branch_id,
            owner_type="branch",
            amount=Decimal(str(input.amount)),
            currency=input.currency,
            destination=input.destination,
            description=input.description
        )
        
        # Get transaction details
        transaction = await db.wallet_transactions.find_one({"_id": result["transaction_id"]})
        
        return WalletTransactionType(
            id=transaction["_id"],
            from_owner_id=transaction.get("fromOwnerId"),
            from_owner_type=transaction.get("fromOwnerType"),
            to_owner_id=transaction.get("toOwnerId"),
            to_owner_type=transaction.get("toOwnerType"),
            amount=transaction["amount"],
            currency=transaction["currency"],
            type=transaction["type"],
            status=transaction["status"],
            description=transaction.get("description"),
            created_at=transaction["createdAt"],
            completed_at=transaction.get("completedAt")
        )
