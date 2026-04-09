"""GraphQL mutations for Branch entity."""

from datetime import datetime
from typing import Optional

import strawberry
from bson import ObjectId
from strawberry.types import Info

from domain.models import Branch, Coordinates
from repositories import (
    branches_repo,
    businesses_repo,
    products_repo,
    store_locations_repo,
)
from services.access_checker import access_checker
from utils.graphql_auth import apply_optional_jwt
from utils.s3 import delete_file

from .inputs import CreateBranchInput, UpdateBranchInput, expand_schedule_input
from .transfer_accounts import (
    build_legacy_phones,
    build_legacy_qr_payments,
    normalize_transfer_accounts,
)
from .types import BranchTipo, BranchType, CoordinatesType
from .utils import branch_to_dict


@strawberry.type
class BranchMutation:
    @strawberry.mutation(description="Crear una nueva sucursal")
    async def create_branch(
        self, info: Info, input: CreateBranchInput, jwt: Optional[str] = None
    ) -> BranchType:
        """
        Create a new branch. Upload images first via POST /upload/branch/avatar
        or POST /upload/branch/cover.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify business exists and user is owner (only owners can create branches)
        await access_checker.require_business_access(
            user_id, input.businessId, require_owner=True
        )

        # Validate tipos is not empty
        if not input.tipos:
            raise Exception("Debe especificar al menos un tipo de establecimiento")

        # Validate paymentMethodIds is not empty
        if not input.paymentMethodIds:
            raise Exception("Debe especificar al menos un método de pago")

        # Verify payment methods exist
        from repositories import payment_methods_repo

        payment_methods = await payment_methods_repo.get_by_ids(input.paymentMethodIds)
        if len(payment_methods) != len(input.paymentMethodIds):
            raise Exception("Uno o más métodos de pago no existen")

        accepted_currency = (
            input.acceptedCurrency.value if input.acceptedCurrency else None
        )

        if input.exchangeRate is not None:
            if input.exchangeRate <= 0:
                raise Exception("exchangeRate debe ser mayor que 0")
            if accepted_currency != "BOTH":
                raise Exception(
                    "exchangeRate solo aplica cuando acceptedCurrency es BOTH"
                )

        normalized_accounts = normalize_transfer_accounts(input.accounts)
        legacy_qr_payments = build_legacy_qr_payments(normalized_accounts)
        legacy_phones = build_legacy_phones(normalized_accounts)

        # Create branch
        branch_id = str(ObjectId())
        branch = Branch(
            id=branch_id,
            businessId=input.businessId,
            name=input.name,
            address=input.address,
            coordinates=Coordinates(
                type="Point", coordinates=[input.coordinates.lng, input.coordinates.lat]
            ),
            phone=input.phone,
            schedule=expand_schedule_input(input.schedule),
            managerIds=input.managerIds or [user_id],
            isActive=True,
            avatar=input.avatar,
            coverImage=input.coverImage,
            socialMedia=input.socialMedia,
            tipos=[t.value for t in input.tipos],
            paymentMethodIds=input.paymentMethodIds,
            wallet={"local": 0.0, "usd": 0.0},
            walletStatus="active",
            useAppMessaging=input.useAppMessaging,
            pickupEnabled=input.pickupEnabled,
            vehicles=[v.value for v in input.vehicles] if input.vehicles else [],
            acceptedCurrency=accepted_currency,
            exchangeRate=input.exchangeRate if accepted_currency == "BOTH" else None,
            accounts=normalized_accounts,
            # Legacy mirrors kept in DB for backward compatibility with old clients.
            qrPayments=legacy_qr_payments,
            phones=legacy_phones,
            cashKycEnabled=input.cashKycEnabled,
            cashKycPolicyVersion=input.cashKycPolicyVersion,
            cashKycMinConfidence=input.cashKycMinConfidence,
            cashKycTtlDays=input.cashKycTtlDays,
            createdAt=datetime.now(),
        )

        # Step 1: Create in MongoDB first
        created_branch = await branches_repo.create(branch)

        # Save location to MongoDB stores_location collection
        await store_locations_repo.upsert(
            store_id=branch_id,
            longitude=input.coordinates.lng,
            latitude=input.coordinates.lat,
            active=True,
        )

        # Sync business-level access to the new branch
        from services.access_manager import access_manager

        await access_manager.sync_business_access_to_new_branch(created_branch.id)

        return BranchType(**branch_to_dict(created_branch))

    @strawberry.mutation(description="Actualizar una sucursal")
    async def update_branch(
        self,
        info: Info,
        branch_id: str,
        input: UpdateBranchInput,
        jwt: Optional[str] = None,
    ) -> BranchType:
        """
        Update branch data. For new images, upload first via POST /upload/branch/avatar
        or POST /upload/branch/cover.
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch exists and user has access
        await access_checker.require_branch_access(user_id, branch_id)

        # Get branch for further operations
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Build updates dict from input
        updates = {}
        if input.name is not None:
            updates["name"] = input.name
        if input.address is not None:
            updates["address"] = input.address
        if input.phone is not None:
            updates["phone"] = input.phone
        if input.schedule is not None:
            updates["schedule"] = expand_schedule_input(input.schedule).model_dump()
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.socialMedia is not None:
            updates["socialMedia"] = input.socialMedia
        if input.managerIds is not None:
            # Only owner can change managers - verify owner access
            business = await businesses_repo.get_by_id(branch.businessId)
            if not business:
                raise Exception("Negocio no encontrado")

            await access_checker.require_business_access(
                user_id, branch.businessId, require_owner=True
            )
            updates["managerIds"] = input.managerIds
        if input.avatar is not None:
            # Delete old avatar if exists
            if branch.avatar:
                await delete_file(branch.avatar)
            updates["avatar"] = input.avatar
        if input.coverImage is not None:
            # Delete old cover if exists
            if branch.coverImage:
                await delete_file(branch.coverImage)
            updates["coverImage"] = input.coverImage
        if input.tipos is not None:
            if not input.tipos:
                raise Exception("Debe especificar al menos un tipo de establecimiento")
            updates["tipos"] = [t.value for t in input.tipos]
        if input.paymentMethodIds is not None:
            if not input.paymentMethodIds:
                raise Exception("Debe especificar al menos un método de pago")
            # Verify payment methods exist
            from repositories import payment_methods_repo

            payment_methods = await payment_methods_repo.get_by_ids(
                input.paymentMethodIds
            )
            if len(payment_methods) != len(input.paymentMethodIds):
                raise Exception("Uno o más métodos de pago no existen")
            updates["paymentMethodIds"] = input.paymentMethodIds
        if input.useAppMessaging is not None:
            updates["useAppMessaging"] = input.useAppMessaging
            # If disabling app delivery, unlink all delivery persons from this branch
            if not input.useAppMessaging and branch.useAppMessaging:
                from repositories.orders_repository import delivery_persons_repo

                await delivery_persons_repo.unlink_all_from_branch(branch_id)
        if input.pickupEnabled is not None:
            updates["pickupEnabled"] = input.pickupEnabled
        if input.vehicles is not None:
            updates["vehicles"] = [v.value for v in input.vehicles]
        if input.acceptedCurrency is not None:
            updates["acceptedCurrency"] = input.acceptedCurrency.value
            # If currency is not BOTH, exchange rate should be cleared.
            if input.acceptedCurrency.value != "BOTH" and input.exchangeRate is None:
                updates["exchangeRate"] = None
        if input.exchangeRate is not None:
            if input.exchangeRate <= 0:
                raise Exception("exchangeRate debe ser mayor que 0")
            target_currency = (
                input.acceptedCurrency.value
                if input.acceptedCurrency is not None
                else branch.acceptedCurrency
            )
            if target_currency != "BOTH":
                raise Exception(
                    "exchangeRate solo aplica cuando acceptedCurrency es BOTH"
                )
            updates["exchangeRate"] = input.exchangeRate
        if input.accounts is not None:
            normalized_accounts = normalize_transfer_accounts(input.accounts)
            updates["accounts"] = normalized_accounts
            # Keep legacy mirrors synchronized from the single source of truth.
            updates["qrPayments"] = build_legacy_qr_payments(normalized_accounts)
            updates["phones"] = build_legacy_phones(normalized_accounts)
        if input.acceptsQvapay is not None:
            updates["acceptsQvapay"] = input.acceptsQvapay
        if input.acceptsZelle is not None:
            updates["acceptsZelle"] = input.acceptsZelle
        if input.qvapayUsername is not None:
            updates["qvapayUsername"] = input.qvapayUsername
        if input.zelleEmail is not None:
            updates["zelleEmail"] = input.zelleEmail
        if input.cashKycEnabled is not None:
            updates["cashKycEnabled"] = input.cashKycEnabled
        if input.cashKycPolicyVersion is not None:
            updates["cashKycPolicyVersion"] = input.cashKycPolicyVersion
        if input.cashKycMinConfidence is not None:
            if input.cashKycMinConfidence < 0 or input.cashKycMinConfidence > 1:
                raise Exception("cashKycMinConfidence debe estar entre 0 y 1")
            updates["cashKycMinConfidence"] = input.cashKycMinConfidence
        if input.cashKycTtlDays is not None:
            if input.cashKycTtlDays <= 0:
                raise Exception("cashKycTtlDays debe ser mayor que 0")
            updates["cashKycTtlDays"] = input.cashKycTtlDays
        if input.forceReverify is not None:
            updates["forceReverify"] = input.forceReverify

        # Handle coordinates update - save to MongoDB stores_location
        if input.coordinates is not None:
            # Use upsert to create if not exists
            await store_locations_repo.upsert(
                store_id=branch_id,
                longitude=input.coordinates.lng,
                latitude=input.coordinates.lat,
                active=branch.isActive,
            )
            # Also update in Qdrant metadata
            updates["coordinates"] = {
                "type": "Point",
                "coordinates": [input.coordinates.lng, input.coordinates.lat],
            }

        # Handle isActive change - sync active status to stores_location
        if input.isActive is not None:
            await store_locations_repo.set_active(
                store_id=branch_id, active=input.isActive
            )

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update branch
        updated_branch = await branches_repo.update(branch_id, updates)
        if not updated_branch:
            raise Exception("Error al actualizar la sucursal")

        return BranchType(**branch_to_dict(updated_branch))

    @strawberry.mutation(description="Eliminar una sucursal")
    async def delete_branch(
        self, info: Info, branch_id: str, jwt: Optional[str] = None
    ) -> bool:
        """
        Delete a branch and all its associated data.
        Only the business owner can delete branches.
        This will also delete:
        - All products associated with the branch
        - The branch location from stores_location
        - Branch images from S3
        """
        apply_optional_jwt(jwt, info)
        user_id = info.context.get("user_id")
        if not user_id:
            raise Exception("Usuario no autenticado")

        # Verify branch exists
        branch = await branches_repo.get_by_id(branch_id)
        if not branch:
            raise Exception("Sucursal no encontrada")

        # Verify user is the business owner (only owner can delete, not managers)
        await access_checker.require_branch_access(
            user_id, branch_id, require_owner=True
        )

        # Delete branch images from S3
        if branch.avatar:
            await delete_file(branch.avatar)
        if branch.coverImage:
            await delete_file(branch.coverImage)

        # Delete all products associated with this branch
        products = await products_repo.get_by_branch(branch_id)
        for product in products:
            if product.image:
                await delete_file(product.image)
            await products_repo.delete(product.id)

        # Delete location from MongoDB stores_location
        await store_locations_repo.delete(branch_id)

        # Delete branch from Qdrant
        deleted = await branches_repo.delete(branch_id)
        if not deleted:
            raise Exception("Error al eliminar la sucursal")

        return True
